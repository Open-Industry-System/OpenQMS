import { describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import CharacteristicEditor from "./CharacteristicEditor";
import type { Characteristic } from "../../types";

const productCharacteristic: Characteristic = {
  id: "char-1",
  kind: "product",
  name: "贴装偏移量",
  specification: "≤ 0.05",
  unit: "mm",
  classification: "CC",
  reference: "DWG-01",
  related_product_characteristic_ids: [],
};

function StatefulEditor({ onChange }: { onChange: (value: Characteristic[]) => void }) {
  const [value, setValue] = useState<Characteristic[]>([]);
  return (
    <CharacteristicEditor
      value={value}
      allowedKind="product"
      productOptions={[]}
      readOnly={false}
      onChange={(nextValue) => { setValue(nextValue); onChange(nextValue); }}
    />
  );
}

describe("CharacteristicEditor", () => {
  it("keeps name, specification and classification separate when adding multiple characteristics", () => {
    const onChange = vi.fn();
    render(<StatefulEditor onChange={onChange} />);

    fireEvent.click(screen.getByText("新增产品特性"));
    fireEvent.change(screen.getByLabelText("特性名称"), { target: { value: "贴装偏移量" } });
    fireEvent.change(screen.getByLabelText("规范／公差"), { target: { value: "≤ 0.05" } });
    fireEvent.click(screen.getByRole("button", { name: "确认特性" }));

    fireEvent.click(screen.getByText("新增产品特性"));
    const nameInputs = screen.getAllByLabelText("特性名称");
    const specificationInputs = screen.getAllByLabelText("规范／公差");
    const classificationInputs = screen.getAllByLabelText("特殊分类");
    fireEvent.change(nameInputs[nameInputs.length - 1], { target: { value: "表面状态" } });
    fireEvent.change(specificationInputs[specificationInputs.length - 1], { target: { value: "无划伤" } });
    fireEvent.mouseDown(classificationInputs[classificationInputs.length - 1]);
    fireEvent.click(screen.getByText("SC", { selector: ".ant-select-item-option-content" }));
    fireEvent.click(screen.getByRole("button", { name: "确认特性" }));

    expect(onChange).toHaveBeenLastCalledWith([
      expect.objectContaining({ name: "贴装偏移量", specification: "≤ 0.05", classification: null }),
      expect.objectContaining({ name: "表面状态", specification: "无划伤", classification: "SC" }),
    ]);
  });

  it("preserves the stable ID when an existing characteristic is renamed", () => {
    const onChange = vi.fn();
    render(
      <CharacteristicEditor
        value={[productCharacteristic]}
        allowedKind="product"
        productOptions={[]}
        readOnly={false}
        onChange={onChange}
      />,
    );

    const nameInput = screen.getByDisplayValue("贴装偏移量");
    fireEvent.change(nameInput, { target: { value: "贴装位置偏差" } });
    fireEvent.blur(nameInput);

    expect(onChange).toHaveBeenLastCalledWith([
      expect.objectContaining({ id: "char-1", name: "贴装位置偏差" }),
    ]);
  });

  it("shows required feedback for an existing blank name without persisting it and recovers with the same UUID", () => {
    const onChange = vi.fn();
    render(<CharacteristicEditor value={[productCharacteristic]} allowedKind="product" productOptions={[]} readOnly={false} onChange={onChange} />);
    const input = screen.getByLabelText("特性名称");
    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.blur(input);
    expect(screen.getByText("请输入特性名称")).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "恢复名称" } });
    fireEvent.blur(input);
    expect(screen.queryByText("请输入特性名称")).not.toBeInTheDocument();
    expect(onChange).toHaveBeenLastCalledWith([expect.objectContaining({ id: "char-1", name: "恢复名称" })]);
  });

  it("shows a legacy reminder without converting or autosaving a missing collection", () => {
    const onChange = vi.fn();
    render(
      <CharacteristicEditor
        value={undefined}
        allowedKind="product"
        productOptions={[]}
        readOnly={false}
        onChange={onChange}
      />,
    );

    expect(screen.getByText("历史功能字段仅供参考，请确认后录入结构化特性。")).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("does not expose process choices while editing a DFMEA product characteristic", () => {
    render(
      <CharacteristicEditor
        value={[productCharacteristic]}
        allowedKind="product"
        productOptions={[]}
        readOnly={false}
        onChange={() => {}}
      />,
    );

    expect(screen.queryByText("关联产品特性")).not.toBeInTheDocument();
    expect(screen.getByText("产品特性")).toBeInTheDocument();
  });
});
