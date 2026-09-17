from __future__ import annotations

import re


class WorkflowRouter:
    """Conservative router between managed PLUS workflows and normal ReAct chat."""

    _CONTROL_WORDS = {
        "继续",
        "确认",
        "取消工作流",
        "查看工作流状态",
        "重新执行上一步",
        "ok",
        "cancel",
    }

    _EXPLANATION_WORDS = ("解释", "原理", "是什么", "介绍", "说明", "为什么")
    _FILE_WORDS = ("有哪些文件", "列出文件", "查看文件", "搜索文件")

    def should_use_workflow(self, message: str, has_active_workflow: bool = False) -> bool:
        text = (message or "").strip().lower()
        if has_active_workflow:
            return True
        if not text:
            return False
        if any(word in text for word in self._EXPLANATION_WORDS):
            return False
        if any(word in text for word in self._FILE_WORDS):
            return False
        return self._looks_like_full_simulation(text)

    def _looks_like_full_simulation(self, text: str) -> bool:
        has_plus = "plus" in text or "土地利用" in text or "lulc" in text
        has_explicit_workflow = any(word in text for word in ("完整流程", "完整工作流", "标准流程"))
        has_simulation = any(word in text for word in ("模拟", "预测", "推演"))
        has_future_year = bool(re.search(r"(?<!\d)(?:19|20)\d{2}(?!\d)", text)) or "未来" in text
        return has_plus and (has_explicit_workflow or (has_simulation and has_future_year))
