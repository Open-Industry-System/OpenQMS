import { create } from "zustand";
import type { ProductLine } from "../types";
import { listProductLines } from "../api/productLine";

const STORAGE_KEY = "openqms_product_line";

interface ProductLineState {
  productLines: ProductLine[];
  selected: string | null;
  setSelected: (code: string | null) => void;
  load: () => Promise<void>;
}

export const useProductLineStore = create<ProductLineState>((set) => ({
  productLines: [],
  selected: localStorage.getItem(STORAGE_KEY),
  setSelected: (code) => {
    if (code) {
      localStorage.setItem(STORAGE_KEY, code);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    set({ selected: code });
  },
  load: async () => {
    try {
      const items = await listProductLines(true);
      const current = useProductLineStore.getState().selected;
      if (current && !items.some((pl) => pl.code === current)) {
        useProductLineStore.getState().setSelected(null);
      }
      set({ productLines: items });
    } catch {
      // silently fail — selector will show empty
    }
  },
}));
