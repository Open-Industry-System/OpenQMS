"""Tests for ERP integration -- mock connector, ingestion, traceability, masking,
date coercion, and DAG gating.

Uses an isolated engine + transaction per test to avoid asyncpg event-loop
contention with the shared application engine.
Database-dependent tests require a running PostgreSQL and DATABASE_URL set.

Run:  DATABASE_URL="postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms" \
      SECRET_KEY=test-secret-key-not-default \
      pytest backend/tests/test_erp.py -v
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import SYSTEM_USER_ID
from app.config import settings
from app.database import Base
from app.models.customer_quality import Customer, ShipmentRecord
from app.models.erp import (
    ERPConnection,
    ERPPurchaseOrder,
    ERPShipment,
    ERPSupplier,
    ERPSyncJob,
)
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition
from app.models.supplier import Supplier
from app.models.user import User
from app.services.erp_connector import MockERPConnector
from app.services.erp_service import (
    ERPIngestionService,
    ERPSyncService,
    ERPTraceabilityService,
)


# ---------------------------------------------------------------------------
# Isolated db fixture -- fresh engine + session per test.
#
# Creating a fresh engine inside each test's event loop avoids the classic
# pytest-asyncio + asyncpg "Future attached to a different loop" errors
# caused by sharing an engine created in a different loop.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Yield a fresh async session with a transaction that is always rolled back."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.connect() as conn:
        async with conn.begin() as tx:
            session_factory = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            session = session_factory(bind=conn)
            try:
                yield session
            finally:
                await session.close()
                await tx.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create and return a test admin user inside the isolated transaction.

    Uses a random UUID to avoid collision with seed data (SYSTEM_USER_ID).
    """
    # Ensure product line exists
    result = await db_session.execute(
        select(ProductLine).where(ProductLine.code == "DC-DC-100")
    )
    if result.scalar_one_or_none() is None:
        db_session.add(ProductLine(code="DC-DC-100", name="DC-DC-100"))
        await db_session.flush()

    # Ensure admin role exists
    result = await db_session.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "admin")
    )
    role = result.scalar_one_or_none()
    if role is None:
        role = RoleDefinition(
            role_key="admin",
            name_zh="管理员",
            name_en="Admin",
            is_system=True,
            is_active=True,
        )
        db_session.add(role)
        await db_session.flush()

    user = User(
        user_id=uuid.uuid4(),
        username=f"test_admin_{uuid.uuid4().hex[:8]}",
        display_name="Test Admin",
        password_hash="hashed",
        role_id=role.id,
        legacy_role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_connection(
    session: AsyncSession, user: User, name: str = "test"
) -> ERPConnection:
    """Create a mock ERP connection and return it (flushed, not committed)."""
    conn = ERPConnection(
        name=name,
        connector_type="mock",
        config={},
        created_by=user.user_id,
        product_line_code="DC-DC-100",
    )
    session.add(conn)
    await session.flush()
    return conn


# ===========================================================================
# TestMockConnector
# ===========================================================================


class TestMockConnector:
    """MockERPConnector returns valid data for all 9 data types."""

    DATA_TYPES = [
        "suppliers",
        "customers",
        "materials",
        "locations",
        "purchase_orders",
        "sales_orders",
        "inventory_balances",
        "shipments",
        "cost_records",
    ]

    @pytest.mark.parametrize("data_type", DATA_TYPES)
    async def test_mock_returns_list(self, data_type):
        """Each fetch_<data_type> should return a non-empty list of dicts."""
        connector = MockERPConnector({})
        method = getattr(connector, f"fetch_{data_type}")
        since = datetime(2000, 1, 1, tzinfo=timezone.utc)
        items = await method(since)
        assert isinstance(items, list), f"{data_type} did not return a list"
        assert len(items) > 0, f"{data_type} returned empty list"

    @pytest.mark.parametrize("data_type", DATA_TYPES)
    async def test_mock_items_have_external_id(self, data_type):
        """Each returned item must contain 'external_id'."""
        connector = MockERPConnector({})
        method = getattr(connector, f"fetch_{data_type}")
        since = datetime(2000, 1, 1, tzinfo=timezone.utc)
        items = await method(since)
        for item in items:
            assert "external_id" in item, f"{data_type} item missing external_id"


# ===========================================================================
# TestIngestion
# ===========================================================================


class TestIngestion:
    """Supplier auto-link, PO reference error, shipment creates ShipmentRecord."""

    @pytest.mark.asyncio
    async def test_supplier_auto_link(self, db_session: AsyncSession, admin_user: User):
        """Supplier ingestion should auto-link when supplier_no matches."""
        suffix = uuid.uuid4().hex[:8]
        supplier_no = f"SUP-{suffix}"

        # Create an OpenQMS supplier
        supplier = Supplier(
            supplier_no=supplier_no,
            name="Test Supplier",
            short_name="TS",
            status="approved",
            created_by=admin_user.user_id,
        )
        db_session.add(supplier)
        await db_session.flush()

        conn = await _create_connection(db_session, admin_user, name="auto-link-test")

        await ERPIngestionService._ingest_suppliers(
            db_session,
            conn.connection_id,
            {
                "external_id": "SUP-EXT",
                "supplier_code": supplier_no,
                "name": "Test Supplier",
            },
        )

        result = await db_session.execute(
            select(ERPSupplier).where(
                ERPSupplier.connection_id == conn.connection_id,
                ERPSupplier.supplier_code == supplier_no,
            )
        )
        erp_sup = result.scalar_one()
        assert erp_sup.link_status == "linked"
        assert erp_sup.openqms_supplier_id == supplier.supplier_id

    @pytest.mark.asyncio
    async def test_po_reference_error_when_supplier_not_found(
        self, db_session: AsyncSession, admin_user: User
    ):
        """PO ingestion with unknown supplier_code sets _reference_errors."""
        conn = await _create_connection(db_session, admin_user, name="po-ref-test")

        await ERPIngestionService._ingest_purchase_orders(
            db_session,
            conn.connection_id,
            {
                "external_id": "PO-1",
                "po_number": "PO-001",
                "line_number": "1",
                "supplier_code": "UNKNOWN-SUP",
                "quantity": 100,
            },
        )

        result = await db_session.execute(
            select(ERPPurchaseOrder).where(ERPPurchaseOrder.po_number == "PO-001")
        )
        po = result.scalar_one()
        assert po.erp_raw_data is not None
        assert po.erp_raw_data.get("_reference_errors") is not None

    @pytest.mark.asyncio
    async def test_ingest_shipment_creates_shipment_record(
        self, db_session: AsyncSession, admin_user: User
    ):
        """Shipment ingestion should create ShipmentRecord and link erp_shipment."""
        # Create customer
        customer = Customer(customer_code="CUST-TEST", name="Test Customer")
        db_session.add(customer)
        await db_session.flush()

        conn = await _create_connection(db_session, admin_user, name="shipment-test")

        # Ingest customer first so openqms_customer_id gets linked
        await ERPIngestionService._ingest_customers(
            db_session,
            conn.connection_id,
            {
                "external_id": "CUST-EXT",
                "customer_code": "CUST-TEST",
                "name": "Test Customer",
            },
        )

        # Ingest shipment
        await ERPIngestionService._ingest_shipments(
            db_session,
            conn.connection_id,
            {
                "external_id": "SHIP-1",
                "shipment_number": "DN-001",
                "line_number": "1",
                "customer_code": "CUST-TEST",
                "lot_no": "LOT-001",
                "quantity": 50,
                "shipment_date": "2026-06-01",
            },
        )

        # Verify ShipmentRecord created
        result = await db_session.execute(
            select(ShipmentRecord).where(ShipmentRecord.batch_no == "LOT-001")
        )
        record = result.scalar_one()
        assert record.quantity == 50
        assert record.customer_id == customer.customer_id

        # Verify erp_shipment linked
        ship_result = await db_session.execute(
            select(ERPShipment).where(ERPShipment.shipment_number == "DN-001")
        )
        ship = ship_result.scalar_one()
        assert ship.link_status == "linked"
        assert ship.openqms_shipment_id == record.shipment_id


# ===========================================================================
# TestTraceability
# ===========================================================================


class TestTraceability:
    @pytest.mark.asyncio
    async def test_traceability_forward(self, db_session: AsyncSession, admin_user: User):
        """Forward traceability returns nodes, edges, and gaps."""
        conn = await _create_connection(db_session, admin_user, name="trace-test")

        # Create supplier
        await ERPIngestionService._ingest_suppliers(
            db_session,
            conn.connection_id,
            {
                "external_id": "SUP-EXT",
                "supplier_code": "SUP-001",
                "name": "Supplier A",
            },
        )
        # Create PO
        await ERPIngestionService._ingest_purchase_orders(
            db_session,
            conn.connection_id,
            {
                "external_id": "PO-EXT",
                "po_number": "PO-001",
                "line_number": "1",
                "supplier_code": "SUP-001",
                "lot_no": "LOT-001",
                "quantity": 100,
            },
        )

        result = await ERPTraceabilityService.query(
            db_session, "LOT-001", "forward"
        )
        assert len(result["nodes"]) >= 2
        # MES gap is expected since there is no MES data
        assert len(result["gaps"]) >= 1


# ===========================================================================
# TestMasking
# ===========================================================================


class TestMasking:
    # -- helper: plain object with bank_info and tax_id attrs ----------
    @staticmethod
    def _make_supplier(bank_info=None, tax_id=None):
        """Build a lightweight object that _mask_entity recognises as a supplier."""
        sup = type("_FauxSupplier", (), {})()
        sup.bank_info = bank_info
        sup.tax_id = tax_id
        return sup

    def test_supplier_masking_for_viewer(self):
        """Viewer (permission_level=1) sees bank_info='***' and tax_id partially masked."""
        from app.api.erp import _mask_entity

        sup = self._make_supplier(
            bank_info={"account": "1234567890"},
            tax_id="91310000MA1FL2XX3X",
        )
        masked = _mask_entity(sup, 1)  # VIEW level
        assert masked.bank_info == "***"
        assert masked.tax_id == "913100****"

    def test_supplier_no_masking_for_manager(self):
        """Manager (permission_level=4) sees full bank_info and tax_id."""
        from app.api.erp import _mask_entity

        sup = self._make_supplier(
            bank_info={"account": "1234567890"},
            tax_id="91310000MA1FL2XX3X",
        )
        masked = _mask_entity(sup, 4)  # APPROVE level
        assert masked.bank_info == {"account": "1234567890"}
        assert masked.tax_id == "91310000MA1FL2XX3X"

    def test_supplier_masking_for_field_qe(self):
        """field_qe (permission_level=2) also sees masked bank_info and tax_id."""
        from app.api.erp import _mask_entity

        sup = self._make_supplier(
            bank_info={"account": "1234567890"},
            tax_id="91310000MA1FL2XX3X",
        )
        masked = _mask_entity(sup, 2)  # CREATE level
        assert masked.bank_info == "***"
        assert masked.tax_id == "913100****"


# ===========================================================================
# TestDateCoercion
# ===========================================================================


class TestDateCoercion:
    def test_coerce_date_from_string(self):
        result = ERPIngestionService._coerce_date("2026-06-01")
        assert result == date(2026, 6, 1)

    def test_coerce_date_from_date(self):
        d = date(2026, 6, 1)
        assert ERPIngestionService._coerce_date(d) == d

    def test_coerce_date_none(self):
        assert ERPIngestionService._coerce_date(None) is None


# ===========================================================================
# TestDAGGating
# ===========================================================================


class TestDAGGating:
    @pytest.mark.asyncio
    async def test_dag_defers_when_upstream_pending(self, db_session: AsyncSession, admin_user: User):
        """Phase 2 job should be deferred if Phase 1 jobs are not completed."""
        conn = await _create_connection(db_session, admin_user, name="dag-defer-test")

        past = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Create a pending Phase 1 job
        job = ERPSyncJob(
            connection_id=conn.connection_id,
            data_type="suppliers",
            status="pending",
            next_run_at=past,
        )
        db_session.add(job)

        # Create a pending Phase 2 job that targets the same connection
        job2 = ERPSyncJob(
            connection_id=conn.connection_id,
            data_type="purchase_orders",
            status="pending",
            next_run_at=past,
        )
        db_session.add(job2)
        await db_session.flush()

        # Try to run a Phase 2 job (purchase_orders) -- should be deferred
        # because Phase 1 (suppliers) is still pending
        result = await ERPSyncService._run_single_sync_job(
            db_session, "purchase_orders"
        )
        assert result["status"] == "deferred"

    @pytest.mark.asyncio
    async def test_dag_runs_when_upstream_completed(self, db_session: AsyncSession, admin_user: User):
        """Phase 2 job should proceed if all Phase 1 jobs are completed."""
        conn = await _create_connection(db_session, admin_user, name="dag-proceed-test")

        # Create completed Phase 1 jobs
        for dt in ("suppliers", "customers", "materials", "locations"):
            job = ERPSyncJob(
                connection_id=conn.connection_id,
                data_type=dt,
                status="completed",
                next_run_at=datetime.now(timezone.utc),
            )
            db_session.add(job)

        # Create a pending Phase 2 job
        job = ERPSyncJob(
            connection_id=conn.connection_id,
            data_type="purchase_orders",
            status="pending",
            next_run_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.flush()

        # Run the Phase 2 job -- should NOT be deferred
        result = await ERPSyncService._run_single_sync_job(
            db_session, "purchase_orders"
        )
        assert result["status"] != "deferred"
