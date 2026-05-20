import { calculateAP } from "./fmea";

// ---------------------------------------------------------------------------
// 1. Failure-mode generation from Chinese function description
// ---------------------------------------------------------------------------

const VERB_PATTERNS: Record<string, string[]> = {
  // 采集 / 收集 / 获取
  "采集": ["无法采集", "采集失效", "采集精度不足", "采集延迟"],
  "收集": ["无法收集", "收集失效", "收集不完整", "收集延迟"],
  "获取": ["无法获取", "获取失效", "获取不完整", "获取延迟"],

  // 传输 / 发送 / 传递
  "传输": ["无法传输", "传输失效", "传输失真", "传输延迟"],
  "发送": ["无法发送", "发送失效", "发送失真", "发送延迟"],
  "传递": ["无法传递", "传递失效", "传递失真", "传递延迟"],

  // 控制 / 调节 / 调控
  "控制": ["无法控制", "控制失效", "控制精度不足", "控制响应慢"],
  "调节": ["无法调节", "调节失效", "调节精度不足", "调节响应慢"],
  "调控": ["无法调控", "调控失效", "调控精度不足", "调控响应慢"],

  // 检测 / 监测 / 识别
  "检测": ["无法检测", "检测失效", "检测精度不足", "误检测"],
  "监测": ["无法监测", "监测失效", "监测精度不足", "误监测"],
  "识别": ["无法识别", "识别失效", "识别精度不足", "误识别"],

  // 保护 / 防护 / 隔离
  "保护": ["保护失效", "无法保护", "保护不足", "保护误动作"],
  "防护": ["防护失效", "无法防护", "防护不足", "防护误动作"],
  "隔离": ["隔离失效", "无法隔离", "隔离不足", "隔离误动作"],

  // 显示 / 指示 / 反馈
  "显示": ["无法显示", "显示失效", "显示错误", "显示延迟"],
  "指示": ["无法指示", "指示失效", "指示错误", "指示延迟"],
  "反馈": ["无法反馈", "反馈失效", "反馈错误", "反馈延迟"],

  // 存储 / 保存 / 记录
  "存储": ["无法存储", "存储失效", "存储丢失", "存储容量不足"],
  "保存": ["无法保存", "保存失效", "保存丢失", "保存容量不足"],
  "记录": ["无法记录", "记录失效", "记录丢失", "记录容量不足"],

  // 供电 / 供能 / 驱动
  "供电": ["无法供电", "供电失效", "供电不足", "供电不稳定"],
  "供能": ["无法供能", "供能失效", "供能不足", "供能不稳定"],
  "驱动": ["无法驱动", "驱动失效", "驱动力不足", "驱动不稳定"],

  // 连接 / 接合 / 固定
  "连接": ["连接失效", "无法连接", "连接松动", "接触不良"],
  "接合": ["接合失效", "无法接合", "接合松动", "接合不良"],
  "固定": ["固定失效", "无法固定", "固定松动", "固定不良"],

  // 密封 / 封闭 / 隔离
  "密封": ["密封失效", "无法密封", "密封不良", "泄漏"],
  "封闭": ["封闭失效", "无法封闭", "封闭不良", "泄漏"],
};

/**
 * Generates failure-mode suggestions from a Chinese function description.
 * Matches known verb patterns; falls back to generic negations.
 */
export function generateFailureModes(functionDesc: string): string[] {
  for (const [verb, modes] of Object.entries(VERB_PATTERNS)) {
    if (functionDesc.includes(verb)) {
      return modes;
    }
  }
  return [
    `${functionDesc}失效`,
    `无法${functionDesc}`,
    `${functionDesc}精度不足`,
    `${functionDesc}延迟`,
  ];
}

// ---------------------------------------------------------------------------
// 2. Failure-chain suggestions (effects + causes)
// ---------------------------------------------------------------------------

const FAILURE_CHAIN_MAP: Record<
  string,
  { effects: string[]; causes: string[] }
> = {
  "无法采集": {
    effects: ["系统数据缺失", "控制决策错误", "功能降级"],
    causes: ["传感器故障", "信号干扰", "线路断路", "接口氧化"],
  },
  "采集精度不足": {
    effects: ["控制偏差", "系统性能下降", "误报警"],
    causes: ["传感器老化", "校准漂移", "温度影响", "电磁干扰"],
  },
  "无法控制": {
    effects: ["系统失控", "设备损坏", "安全风险"],
    causes: ["执行器故障", "控制算法缺陷", "反馈信号丢失", "电源异常"],
  },
  "密封失效": {
    effects: ["介质泄漏", "环境污染", "设备腐蚀", "安全风险"],
    causes: ["密封件老化", "安装不当", "材料选型错误", "温度超限"],
  },
  "连接失效": {
    effects: ["电路断开", "信号中断", "功能丧失", "系统停机"],
    causes: ["接触不良", "焊接缺陷", "振动疲劳", "腐蚀"],
  },
};

const DEFAULT_EFFECTS = ["功能降级", "系统性能下降"];
const DEFAULT_CAUSES = ["零部件老化", "环境因素", "制造缺陷"];

/**
 * Returns suggested failure effects and causes for a given failure mode.
 */
export function suggestFailureChain(failureMode: string): {
  effects: string[];
  causes: string[];
} {
  for (const [key, chain] of Object.entries(FAILURE_CHAIN_MAP)) {
    if (failureMode.includes(key)) {
      return chain;
    }
  }
  return { effects: DEFAULT_EFFECTS, causes: DEFAULT_CAUSES };
}

// ---------------------------------------------------------------------------
// 3. Optimization hints by AP level
// ---------------------------------------------------------------------------

/**
 * Returns a Chinese hint about what to optimize based on AP level.
 */
export function getOptimizationHint(ap: "H" | "M" | "L"): string {
  switch (ap) {
    case "H":
      return "高优先级：必须采取优化措施以降低严重度(S)或发生度(O)，或提高探测度(D)。建议设计变更或增加冗余。";
    case "M":
      return "中优先级：建议采取优化措施，重点改进探测手段或降低发生度。";
    case "L":
      return "低优先级：当前风险可接受，可保持现有控制措施，持续监控即可。";
    default:
      return "";
  }
}

// ---------------------------------------------------------------------------
// 4. Prevention / detection measure suggestions
// ---------------------------------------------------------------------------

/**
 * Returns prevention and detection measure suggestions based on failure mode
 * and Action Priority.
 */
export function suggestMeasures(
  failureMode: string,
  ap: "H" | "M" | "L"
): { prevention: string[]; detection: string[] } {
  const prevention: string[] = [];
  const detection: string[] = [];

  // AP-level base measures
  if (ap === "H") {
    prevention.push(
      "冗余设计（双通道/备份）",
      "选用更高可靠性等级元器件",
      "降额设计",
      "失效安全设计"
    );
    detection.push(
      "在线实时监测",
      "自诊断功能",
      "出厂100%功能测试"
    );
  } else if (ap === "M") {
    prevention.push(
      "优化设计参数",
      "增加防错结构",
      "选用成熟工艺"
    );
    detection.push(
      "定期功能测试",
      "过程巡检",
      "来料检验"
    );
  } else {
    prevention.push("标准化设计", "选用合格供应商物料");
    detection.push("常规检验", "用户反馈跟踪");
  }

  // Mode-specific measures
  if (/采集|检测|监测|识别/.test(failureMode)) {
    prevention.push("传感器冗余布置", "信号滤波设计");
    detection.push("传感器信号校验", "标定周期缩短");
  }

  if (/密封|封闭|泄漏/.test(failureMode)) {
    prevention.push("双重密封结构", "密封槽优化设计");
    detection.push("气密性测试", "泄漏监测");
  }

  if (/连接|接合|固定|接触/.test(failureMode)) {
    prevention.push("防松结构设计", "镀金/镀银处理");
    detection.push("接触电阻测试", "振动试验验证");
  }

  return { prevention, detection };
}

// ---------------------------------------------------------------------------
// 5. Risk analysis composition
// ---------------------------------------------------------------------------

/**
 * Composes RPN calculation, AP lookup, and optimization hint.
 */
export function analyzeRisk(
  s: number,
  o: number,
  d: number
): { rpn: number; ap: "H" | "M" | "L" | ""; hint: string } {
  const rpn = s * o * d;
  const ap = calculateAP(s, o, d);
  const hint = ap ? getOptimizationHint(ap as "H" | "M" | "L") : "";
  return { rpn, ap, hint };
}
