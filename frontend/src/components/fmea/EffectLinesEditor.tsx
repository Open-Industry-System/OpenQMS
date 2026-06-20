import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Button } from "antd";
import type { ReactElement } from "react";
import type { GraphNode } from "../../types";
import SmartSuggestionDropdown from "../dfmea/SmartSuggestionDropdown";

export interface EffectLinesEditorProps {
  effectIds: string[];
  nodeMap: Map<string, GraphNode>;
  fmeaId: string;
  functionDescription: string;
  failureModeName: string;
  disabled: boolean;
  updateNode: (nodeId: string, field: string, value: unknown) => void;
  onAddEffect: () => void;
  onDeleteEffect: (effectId: string) => void;
}

export default function EffectLinesEditor(props: EffectLinesEditorProps): ReactElement {
  const {
    effectIds, nodeMap, fmeaId, functionDescription, failureModeName,
    disabled, updateNode, onAddEffect, onDeleteEffect,
  } = props;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {effectIds.map((effectId) => {
        const node = nodeMap.get(effectId);
        return (
          <div key={effectId} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <SmartSuggestionDropdown
              triggerType="failure_effect"
              context={{ failure_mode: failureModeName, function_description: functionDescription }}
              fmeaId={fmeaId}
              value={node?.name || ""}
              onChange={(val: string) => updateNode(effectId, "name", val)}
              onSelect={(s) => updateNode(effectId, "name", s.name)}
              disabled={disabled}
            />
            {!disabled && (
              <Button
                size="small"
                type="text"
                danger
                icon={<DeleteOutlined />}
                onClick={() => onDeleteEffect(effectId)}
                aria-label="删除后果"
              />
            )}
          </div>
        );
      })}
      {!disabled && (
        <Button size="small" type="dashed" icon={<PlusOutlined />} onClick={onAddEffect}>
          添加后果
        </Button>
      )}
    </div>
  );
}
