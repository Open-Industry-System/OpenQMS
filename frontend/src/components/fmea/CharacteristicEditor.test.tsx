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

    fireEvent.click(screen.getByText("Add Product characteristic"));
    fireEvent.change(screen.getByLabelText("Characteristic name"), { target: { value: "贴装偏移量" } });
    fireEvent.change(screen.getByLabelText("Specification / tolerance"), { target: { value: "≤ 0.05" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm characteristic" }));

    fireEvent.click(screen.getByText("Add Product characteristic"));
    const nameInputs = screen.getAllByLabelText("Characteristic name");
    const specificationInputs = screen.getAllByLabelText("Specification / tolerance");
    const classificationInputs = screen.getAllByLabelText("Special classification");
    fireEvent.change(nameInputs[nameInputs.length - 1], { target: { value: "表面状态" } });
    fireEvent.change(specificationInputs[specificationInputs.length - 1], { target: { value: "无划伤" } });
    fireEvent.mouseDown(classificationInputs[classificationInputs.length - 1]);
    fireEvent.click(screen.getByText("SC", { selector: ".ant-select-item-option-content" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm characteristic" }));

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
    const input = screen.getByLabelText("Characteristic name");
    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.blur(input);
    expect(screen.getByText("Please enter a characteristic name")).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "恢复名称" } });
    fireEvent.blur(input);
    expect(screen.queryByText("Please enter a characteristic name")).not.toBeInTheDocument();
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

    expect(screen.getByText("Legacy function fields are for reference only; please review and enter structured characteristics.")).toBeInTheDocument();
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

    expect(screen.queryByText("Linked product characteristic")).not.toBeInTheDocument();
    expect(screen.getByText("Product characteristic")).toBeInTheDocument();
  });
});
