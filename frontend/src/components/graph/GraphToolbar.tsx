import { Button, Space, Tooltip, Segmented } from "antd";
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
import type { GraphDirection, GraphLayout } from "../../utils/graphLayout";

interface GraphToolbarProps {
  layout: GraphLayout;
  direction: GraphDirection;
  onLayoutChange: (layout: GraphLayout) => void;
  onDirectionChange: (direction: GraphDirection) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
  onDownload: () => void;
}

export default function GraphToolbar({
  layout,
  direction,
  onLayoutChange,
  onDirectionChange,
  onZoomIn,
  onZoomOut,
  onFitView,
  onDownload,
}: GraphToolbarProps) {
  const { t } = useTranslation("graph");
  const isDagre = layout === "dagre";
  return (
    <Space wrap>
      <Tooltip title={t("toolbar.hierarchical")}>
        <Button
          icon={<ApartmentOutlined />}
          type={isDagre ? "primary" : "default"}
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
      <Tooltip title={isDagre ? "" : t("toolbar.directionDisabledHint")}>
        <Segmented
          value={direction}
          onChange={(val) => onDirectionChange(val as GraphDirection)}
          disabled={!isDagre}
          options={[
            { label: t("toolbar.directionTB"), value: "TB" },
            { label: t("toolbar.directionLR"), value: "LR" },
          ]}
        />
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
