import { useEffect, useState } from "react";
import { Tag } from "antd";
import { useNavigate } from "react-router-dom";
import client from "../../api/client";

export default function SupplierBadge({
  supplierId,
}: {
  supplierId: string | null;
}) {
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
      {name || "供应商"}
    </Tag>
  );
}
