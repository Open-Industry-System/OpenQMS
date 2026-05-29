import { useEffect, useState } from "react";
import { Tag } from "antd";
import { useNavigate } from "react-router-dom";
import client from "../../api/client";

export default function SpecialCharacteristicTag({
  scId,
}: {
  scId: string | null;
}) {
  const navigate = useNavigate();
  const [code, setCode] = useState<string>("");

  useEffect(() => {
    if (!scId) return;
    client.get(`/special-characteristics/${scId}`).then((r) => {
      setCode(r.data.sc_code);
    });
  }, [scId]);

  if (!scId) return null;

  return (
    <Tag
      color="purple"
      style={{ cursor: "pointer" }}
      onClick={() => navigate(`/special-characteristics/${scId}`)}
    >
      {code || "SC"}
    </Tag>
  );
}
