import { useEffect, useState } from "react";
import { Tag } from "antd";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import client from "../../api/client";

interface FMEAInfo {
  fmea_id: string;
  document_no: string;
}

export default function RelatedFMEALink({
  fmeaRefId,
  fmeaNodeId,
}: {
  fmeaRefId: string | null;
  fmeaNodeId?: string | null;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation("capa");
  const [fmea, setFmea] = useState<FMEAInfo | null>(null);

  useEffect(() => {
    if (!fmeaRefId) return;
    client.get(`/fmea/${fmeaRefId}`).then((r) => {
      setFmea({ fmea_id: r.data.fmea_id, document_no: r.data.document_no });
    });
  }, [fmeaRefId]);

  if (!fmea) return null;

  const handleClick = () => {
    const url = fmeaNodeId
      ? `/fmea/${fmea.fmea_id}?node=${fmeaNodeId}`
      : `/fmea/${fmea.fmea_id}`;
    navigate(url);
  };

  return (
    <Tag color="blue" style={{ cursor: "pointer" }} onClick={handleClick}>
      {fmea.document_no}
      {fmeaNodeId && t("fmea.failureModeSuffix")}
    </Tag>
  );
}
