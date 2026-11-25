import { useState } from "react";
import { Alert, Button, Card, Input, Select, Space, Typography } from "antd";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import type { Characteristic } from "../../types";
import { tr, useTr } from "../../i18n/tr";

export interface CharacteristicEditorProps {
  value: Characteristic[] | null | undefined;
  allowedKind: "product" | "process";
  productOptions: { id: string; name: string }[];
  readOnly: boolean;
  onChange: (value: Characteristic[]) => void;
}

type DraftCharacteristic = Omit<Characteristic, "id">;

const emptyDraft = (kind: Characteristic["kind"]): DraftCharacteristic => ({
  kind,
  name: "",
  specification: null,
  unit: null,
  classification: null,
  reference: null,
  related_product_characteristic_ids: [],
});

export default function CharacteristicEditor({
  value,
  allowedKind,
  productOptions,
  readOnly,
  onChange,
}: CharacteristicEditorProps) {
  useTr();
  const [draft, setDraft] = useState<DraftCharacteristic | null>(null);
  const [draftNameError, setDraftNameError] = useState(false);
  const [edits, setEdits] = useState<Record<string, Partial<Characteristic>>>({});
  const characteristics = value ?? [];
  const legacy = value == null;
  const kindLabel = allowedKind === "product" ? tr("Produktmerkmal", "Product characteristic") : tr("Prozessmerkmal", "Process characteristic");

  const updateDraft = <K extends keyof DraftCharacteristic>(key: K, nextValue: DraftCharacteristic[K]) => {
    if (!draft) return;
    setDraft({ ...draft, [key]: nextValue });
    if (key === "name" && String(nextValue).trim()) setDraftNameError(false);
  };

  const commitDraft = () => {
    if (!draft) return;
    if (!draft.name.trim()) {
      setDraftNameError(true);
      return;
    }
    onChange([
      ...characteristics,
      { ...draft, id: crypto.randomUUID(), name: draft.name.trim() },
    ]);
    setDraft(null);
    setDraftNameError(false);
  };

  const setExistingEdit = (id: string, patch: Partial<Characteristic>) => {
    setEdits((current) => ({ ...current, [id]: { ...current[id], ...patch } }));
  };

  const commitExisting = (characteristic: Characteristic) => {
    const patch = edits[characteristic.id];
    if (!patch) return;
    const next = { ...characteristic, ...patch };
    if (!next.name.trim()) return;
    onChange(characteristics.map((item) => item.id === characteristic.id ? { ...next, name: next.name.trim() } : item));
    setEdits((current) => {
      const { [characteristic.id]: _removed, ...remaining } = current;
      return remaining;
    });
  };

  const currentValue = (characteristic: Characteristic): Characteristic => ({
    ...characteristic,
    ...edits[characteristic.id],
  });

  return (
    <Space direction="vertical" size={8} style={{ width: "100%" }}>
      {legacy && (
        <Alert
          type="info"
          showIcon
          message={tr("Historische Funktionsfelder dienen nur als Referenz; bitte prüfen und strukturierte Merkmale erfassen.", "Legacy function fields are for reference only; please review and enter structured characteristics.")}
        />
      )}
      {characteristics.map((characteristic) => {
        const current = currentValue(characteristic);
        return (
          <Card key={characteristic.id} size="small" style={{ marginBottom: 0 }}>
            <Space direction="vertical" size={6} style={{ width: "100%" }}>
              <Typography.Text strong>{kindLabel}</Typography.Text>
              <Input
                aria-label={tr("Merkmalsname", "Characteristic name")}
                value={current.name}
                status={!current.name.trim() ? "error" : undefined}
                aria-invalid={!current.name.trim()}
                disabled={readOnly}
                onChange={(event) => setExistingEdit(characteristic.id, { name: event.target.value })}
                onBlur={() => commitExisting(characteristic)}
              />
              {!current.name.trim() && <Typography.Text type="danger">{tr("Bitte Merkmalsnamen eingeben", "Please enter a characteristic name")}</Typography.Text>}
              <Input
                aria-label={tr("Spezifikation / Toleranz", "Specification / tolerance")}
                value={current.specification ?? ""}
                disabled={readOnly}
                onChange={(event) => setExistingEdit(characteristic.id, { specification: event.target.value || null })}
                onBlur={() => commitExisting(characteristic)}
              />
              <Space wrap>
                <Input
                  aria-label={tr("Einheit", "Unit")}
                  value={current.unit ?? ""}
                  disabled={readOnly}
                  onChange={(event) => setExistingEdit(characteristic.id, { unit: event.target.value || null })}
                  onBlur={() => commitExisting(characteristic)}
                  style={{ width: 96 }}
                />
                <Select
                  aria-label={tr("Besondere Klassifizierung", "Special classification")}
                  value={current.classification ?? undefined}
                  disabled={readOnly}
                  allowClear
                  placeholder={tr("Besondere Klassifizierung", "Special classification")}
                  options={[{ value: "CC", label: "CC" }, { value: "SC", label: "SC" }]}
                  onChange={(classification) => {
                    onChange(characteristics.map((item) => item.id === characteristic.id ? { ...item, classification: classification ?? null } : item));
                  }}
                  style={{ minWidth: 110 }}
                />
                <Input
                  aria-label={tr("Grundlage", "Basis")}
                  value={current.reference ?? ""}
                  disabled={readOnly}
                  onChange={(event) => setExistingEdit(characteristic.id, { reference: event.target.value || null })}
                  onBlur={() => commitExisting(characteristic)}
                  style={{ minWidth: 140 }}
                />
              </Space>
              {allowedKind === "process" && (
                <Select
                  aria-label={tr("Verknüpftes Produktmerkmal", "Linked product characteristic")}
                  mode="multiple"
                  value={current.related_product_characteristic_ids}
                  disabled={readOnly}
                  placeholder={tr("Verknüpftes Produktmerkmal", "Linked product characteristic")}
                  options={productOptions.map((option) => ({ value: option.id, label: option.name }))}
                  onChange={(relatedProductCharacteristicIds) => {
                    onChange(characteristics.map((item) => item.id === characteristic.id ? {
                      ...item,
                      related_product_characteristic_ids: relatedProductCharacteristicIds,
                    } : item));
                  }}
                />
              )}
              {!readOnly && (
                <Button
                  size="small"
                  danger
                  type="text"
                  icon={<DeleteOutlined />}
                  aria-label={tr(`${kindLabel} löschen`, `Delete ${kindLabel}`)}
                  onClick={() => onChange(characteristics.filter((item) => item.id !== characteristic.id))}
                >
                  {tr("Löschen", "Delete")}
                </Button>
              )}
            </Space>
          </Card>
        );
      })}
      {draft && (
        <Card size="small" style={{ marginBottom: 0 }}>
          <Space direction="vertical" size={6} style={{ width: "100%" }}>
            <Typography.Text strong>{tr(`${kindLabel} hinzufügen`, `Add ${kindLabel}`)}</Typography.Text>
            <Input
              aria-label={tr("Merkmalsname", "Characteristic name")}
              value={draft.name}
              status={draftNameError ? "error" : undefined}
              placeholder={tr("Bitte Merkmalsnamen eingeben", "Please enter a characteristic name")}
              onChange={(event) => updateDraft("name", event.target.value)}
            />
            {draftNameError && <Typography.Text type="danger">{tr("Bitte Merkmalsnamen eingeben", "Please enter a characteristic name")}</Typography.Text>}
            <Input
              aria-label={tr("Spezifikation / Toleranz", "Specification / tolerance")}
              value={draft.specification ?? ""}
              placeholder={tr("Spezifikation / Toleranz", "Specification / tolerance")}
              onChange={(event) => updateDraft("specification", event.target.value || null)}
            />
            <Space wrap>
              <Input
                aria-label={tr("Einheit", "Unit")}
                value={draft.unit ?? ""}
                placeholder={tr("Einheit", "Unit")}
                onChange={(event) => updateDraft("unit", event.target.value || null)}
                style={{ width: 96 }}
              />
              <Select
                aria-label={tr("Besondere Klassifizierung", "Special classification")}
                value={draft.classification ?? undefined}
                allowClear
                placeholder={tr("Besondere Klassifizierung", "Special classification")}
                options={[{ value: "CC", label: "CC" }, { value: "SC", label: "SC" }]}
                onChange={(classification) => updateDraft("classification", classification ?? null)}
                style={{ minWidth: 110 }}
              />
              <Input
                aria-label={tr("Grundlage", "Basis")}
                value={draft.reference ?? ""}
                placeholder={tr("Grundlage", "Basis")}
                onChange={(event) => updateDraft("reference", event.target.value || null)}
                style={{ minWidth: 140 }}
              />
            </Space>
            {allowedKind === "process" && (
              <Select
                aria-label={tr("Verknüpftes Produktmerkmal", "Linked product characteristic")}
                mode="multiple"
                value={draft.related_product_characteristic_ids}
                placeholder={tr("Verknüpftes Produktmerkmal", "Linked product characteristic")}
                options={productOptions.map((option) => ({ value: option.id, label: option.name }))}
                onChange={(relatedProductCharacteristicIds) => updateDraft("related_product_characteristic_ids", relatedProductCharacteristicIds)}
              />
            )}
            <Space>
              <Button size="small" type="primary" onClick={commitDraft}>{tr("Merkmal bestätigen", "Confirm characteristic")}</Button>
              <Button size="small" onClick={() => { setDraft(null); setDraftNameError(false); }}>{tr("Abbrechen", "Cancel")}</Button>
            </Space>
          </Space>
        </Card>
      )}
      {!readOnly && !draft && (
        <Button size="small" icon={<PlusOutlined />} onClick={() => setDraft(emptyDraft(allowedKind))}>
          {tr(`${kindLabel} hinzufügen`, `Add ${kindLabel}`)}
        </Button>
      )}
    </Space>
  );
}
