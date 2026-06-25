// frontend/src/utils/pfmeaRules.ts

export interface FailureChain {
  effects: string[];
  causes: string[];
}

const VERB_PATTERNS: Record<string, string[]> = {
  焊接: ['焊点虚焊', '焊点桥连', '焊料不足', '焊点气孔'],
  装配: ['装配错位', '漏装', '错装', '装配过紧/过松'],
  注塑: ['缺料', '飞边', '缩水', '气泡'],
  涂装: ['涂层不均', '漏涂', '涂层过厚/过薄', '色差'],
  压装: ['压装不到位', '压装过载', '压装偏斜', '压装扭矩不稳'],
  贴装: ['贴装偏移', '贴装漏件', '贴装反件', '贴装压力异常'],
};

const FAILURE_CHAIN_MAP: Record<string, FailureChain> = {
  贴装偏移: {
    effects: ['电控板功能丧失', '整机无法启动', '客户退货'],
    causes: ['贴装吸嘴磨损', '贴装压力设定偏小', '设备校准漂移', '来料器件偏置'],
  },
  压装不到位: {
    effects: ['连接松动', '异响', '功能间歇性失效'],
    causes: ['压头行程未校准', '压力传感器漂移', '来料尺寸超差', '操作未按SOP'],
  },
  焊点虚焊: {
    effects: ['电路断开', '信号中断', '功能丧失'],
    causes: ['焊接温度不足', '焊膏活性不足', '贴装压力不足', '环境湿度过高'],
  },
};

const M4_CAUSE_HINTS: Record<string, string[]> = {
  Man: ['操作未按SOP', '培训不足', '疲劳/疏忽', '人员换线未验证'],
  Machine: ['设备校准漂移', '设备磨损', '设备参数漂移', '预防性维护缺失'],
  Material: ['来料尺寸超差', '来料材质不符', '辅料过期', '批次不一致'],
  Environment: ['温湿度超范围', '粉尘/洁净度不足', '静电(ESD)', '照明不足'],
};

export function usePfmeaRules() {
  const generateFailureModes = (stepFunctionText: string): string[] => {
    const text = stepFunctionText ?? '';
    for (const verb of Object.keys(VERB_PATTERNS)) {
      if (text.includes(verb)) return VERB_PATTERNS[verb];
    }
    return [];
  };

  const suggestFailureChain = (failureMode: string): FailureChain =>
    FAILURE_CHAIN_MAP[failureMode] ?? { effects: [], causes: [] };

  const suggest4MCauses = (): Record<string, string[]> => ({ ...M4_CAUSE_HINTS });

  return { generateFailureModes, suggestFailureChain, suggest4MCauses };
}
