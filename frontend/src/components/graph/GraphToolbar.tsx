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
  return (
    <Space wrap>
      <Tooltip title="层次布局">
        <Button
          icon={<ApartmentOutlined />}
          type={layout === "dagre" ? "primary" : "default"}
          onClick={() => onLayoutChange("dagre")}
        >
          层次
        </Button>
      </Tooltip>
      <Tooltip title="力导向布局">
        <Button
          icon={<BranchesOutlined />}
          type={layout === "force" ? "primary" : "default"}
          onClick={() => onLayoutChange("force")}
        >
          力导向
        </Button>
      </Tooltip>
      <Tooltip title="紧凑树">
        <Button
          icon={<ColumnWidthOutlined />}
          type={layout === "compact-box" ? "primary" : "default"}
          onClick={() => onLayoutChange("compact-box")}
        >
          紧凑树
        </Button>
      </Tooltip>
      <Tooltip title="放大">
        <Button icon={<ZoomInOutlined />} onClick={onZoomIn} />
      </Tooltip>
      <Tooltip title="缩小">
        <Button icon={<ZoomOutOutlined />} onClick={onZoomOut} />
      </Tooltip>
      <Tooltip title="适应画布">
        <Button icon={<FullscreenOutlined />} onClick={onFitView} />
      </Tooltip>
      <Tooltip title="下载快照">
        <Button icon={<DownloadOutlined />} onClick={onDownload} />
      </Tooltip>
    </Space>
  );
}
