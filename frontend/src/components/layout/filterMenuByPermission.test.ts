import { describe, it, expect } from "vitest";
import { filterMenuByPermission, type MenuItem } from "./AppLayout";
import type { ModuleKey } from "../../hooks/usePermission";

const canViewNone = (_m: ModuleKey) => false;
const canViewOnly = (...mods: ModuleKey[]) => (m: ModuleKey) => mods.includes(m);

describe("filterMenuByPermission", () => {
  it("无 module/adminOnly 的组会递归过滤其子项", () => {
    const items: MenuItem[] = [
      {
        key: "grp:admin",
        label: "系统设置",
        children: [
          { key: "/admin/users", label: "用户管理", adminOnly: true },
          {
            key: "grp:integration",
            label: "系统集成",
            children: [
              { key: "grp:mes", label: "MES", module: "mes", children: [
                { key: "/mes/dashboard", label: "MES 看板", module: "mes" },
              ]},
            ],
          },
        ],
      },
    ];
    // 非 admin、无任何模块权限 → 子树全空，整组隐藏
    expect(filterMenuByPermission(items, canViewNone, false)).toEqual([]);
  });

  it("只保留有权限的集成子组，隐藏无权限的", () => {
    const items: MenuItem[] = [
      {
        key: "grp:integration",
        label: "系统集成",
        children: [
          { key: "grp:mes", label: "MES", module: "mes", children: [
            { key: "/mes/dashboard", label: "MES 看板", module: "mes" },
          ]},
          { key: "grp:plm", label: "PLM", module: "plm", children: [
            { key: "/plm/dashboard", label: "PLM 看板", module: "plm" },
          ]},
        ],
      },
    ];
    const out = filterMenuByPermission(items, canViewOnly("mes"), false);
    expect(out).toHaveLength(1);
    expect(out[0].children?.map((c) => c.key)).toEqual(["grp:mes"]);
  });

  it("adminOnly 子项对非 admin 隐藏，对 admin 显示", () => {
    const items: MenuItem[] = [
      { key: "grp:admin", label: "系统设置", children: [
        { key: "/admin/users", label: "用户管理", adminOnly: true },
      ]},
    ];
    expect(filterMenuByPermission(items, canViewNone, false)).toEqual([]); // 非 admin：唯一子项被滤，父组空 → 隐藏
    const out = filterMenuByPermission(items, canViewNone, true);           // admin：保留
    expect(out[0].children?.map((c) => c.key)).toEqual(["/admin/users"]);
  });

  it("无 children 的叶子项不受递归影响", () => {
    const items: MenuItem[] = [{ key: "/dashboard", label: "看板" }];
    expect(filterMenuByPermission(items, canViewNone, false)).toHaveLength(1);
  });
});
