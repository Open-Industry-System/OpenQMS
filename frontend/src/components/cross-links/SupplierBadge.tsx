import { useEffect, useState } from "react";
import { Tag } from "antd";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import client from "../../api/client";

export default function SupplierBadge({
  supplierId,
}: {
  supplierId: string | null;
}) {
  const { t } = useTranslation("supplier");
  const navigate = useNavigate();
  const [name, setName] = useState<string>("");

  useEffect(() => {
    if (!supplierId) return;
    client.get(`/suppliers/${supplierId}`).then((r) => {
      setName(r.data.name);
    });
  }, [supplierId]);

  if (!supplierId) return null;

  return (
    <Tag
      color="green"
      style={{ cursor: "pointer" }}
      onClick={() => navigate(`/suppliers/${supplierId}`)}
    >
      {name || t("supplier")}
    </Tag>
  );
}
