import { Button, Space, Tooltip } from "antd";
import {
  ZoomInOutlined,
  ZoomOutOutlined,
  FullscreenOutlined,
  DownloadOutlined,
  ColumnWidthOutlined,
  BranchesOutlined,
  ApartmentOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";

export type GraphLayout = "dagre" | "force" | "compact-box";

interface GraphToolbarProps {
  layout: GraphLayout;
  onLayoutChange: (layout: GraphLayout) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
  onDownload: () => void;
}

export default function GraphToolbar({
  layout,
  onLayoutChange,
  onZoomIn,
  onZoomOut,
  onFitView,
  onDownload,
}: GraphToolbarProps) {
  const { t } = useTranslation("graph");
  return (
    <Space wrap>
      <Tooltip title={t("toolbar.hierarchical")}>
        <Button
          icon={<ApartmentOutlined />}
          type={layout === "dagre" ? "primary" : "default"}
          onClick={() => onLayoutChange("dagre")}
        >
          {t("toolbar.hierarchical")}
        </Button>
      </Tooltip>
      <Tooltip title={t("toolbar.force")}>
        <Button
          icon={<BranchesOutlined />}
          type={layout === "force" ? "primary" : "default"}
          onClick={() => onLayoutChange("force")}
        >
          {t("toolbar.force")}
        </Button>
      </Tooltip>
      <Tooltip title={t("toolbar.compactTree")}>
        <Button
          icon={<ColumnWidthOutlined />}
          type={layout === "compact-box" ? "primary" : "default"}
          onClick={() => onLayoutChange("compact-box")}
        >
          {t("toolbar.compactTree")}
        </Button>
      </Tooltip>
      <Tooltip title={t("toolbar.zoomIn")}>
        <Button icon={<ZoomInOutlined />} onClick={onZoomIn} />
      </Tooltip>
      <Tooltip title={t("toolbar.zoomOut")}>
        <Button icon={<ZoomOutOutlined />} onClick={onZoomOut} />
      </Tooltip>
      <Tooltip title={t("toolbar.fitView")}>
        <Button icon={<FullscreenOutlined />} onClick={onFitView} />
      </Tooltip>
      <Tooltip title={t("toolbar.download")}>
        <Button icon={<DownloadOutlined />} onClick={onDownload} />
      </Tooltip>
    </Space>
  );
}
