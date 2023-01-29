import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

import detect.check_utils as check_utils

from .views import View, ViewHierarchy

GRAPHICAL_VIEW_CLASSES = {
    "android.widget.ImageView",
    "android.widget.ImageButton",
    "android.widget.CheckBox",
    "android.support.v7.widget.AppCompatImageButton",
    "android.support.v7.widget.AppCompatImageView",
    "android.support.v7.view.menu.ActionMenuItemView",
    "android.support.design.widget.FloatingActionButton",
    "com.google.android.material.floatingactionbutton.FloatingActionButton",
}


class ResultCode:
    PASSED = "PASSED"
    CHECK_NOT_RUN = "CHECK_NOT_RUN"
    MISSING_SPEAKABLE_TEXT = "MISSING_SPEAKABLE_TEXT"
    MISSING_HINT_TEXT = "MISSING_HINT_TEXT"
    MISSING_HINT_TEXT_WITH_CONT_DESC = "MISSING_HINT_TEXT_WITH_CONT_DESC"
    HINT_TEXT_WITH_CONT_DESC = "HINT_TEXT_WITH_CONT_DESC"
    REDUNDANT_DESC = "REDUNDANT_DESC"
    UNINFORMATIVE_DESC = "UNINFORMATIVE_DESC"
    CLICKABLE_SAME_SPEAKABLE_TEXT = "CLICKABLE_SAME_SPEAKABLE_TEXT"
    NON_CLICKABLE_SAME_SPEAKABLE_TEXT = "CLICKABLE_SAME_SPEAKABLE_TEXT"


@dataclass(frozen=True)
class CheckResult:
    check_name: str
    result_code: str
    result_id: str
    view_uuid: str
    resource_id: str
    class_name: str
    content_desc: str
    hint_text: str
    text: str
    path: str
    fail_bounds: Dict[str, int]
    parent_bounds: Optional[Dict[str, int]]


class Check:
    """
    Base check class that all accessibility checks inherit from.
    get_result_code() and is_eligible() must be overriden in all Check derived classes.
    """

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description

    def run(self, view_hierarchy: ViewHierarchy) -> List[CheckResult]:
        results: List[CheckResult] = []
        for view in view_hierarchy.get_views():
            if not self.is_eligible(view):
                result_code = ResultCode.CHECK_NOT_RUN
            elif not self.is_visible(view):
                result_code = ResultCode.CHECK_NOT_RUN
            else:
                result_code = self.get_result_code(view)

            if result_code == ResultCode.CHECK_NOT_RUN:
                continue

            results.append(
                CheckResult(
                    check_name=self.name,
                    result_code=result_code,
                    result_id=uuid.uuid4().hex[:16],
                    view_uuid=view_hierarchy.uuid,
                    resource_id=view.resource_id,
                    class_name=view.class_name,
                    content_desc=view.content_desc,
                    hint_text=view.hint_text,
                    text=view.text,
                    path=view.path,
                    fail_bounds=view.rect,
                    parent_bounds=view.parent.rect if view.parent else None,
                )
            )
        return results

    def get_result_code(self, view: View) -> str:
        raise NotImplementedError()

    def is_eligible(self, view: View) -> bool:
        raise NotImplementedError()

    def is_visible(self, view: View) -> bool:
        left = view.rect["left"]
        right = view.rect["right"]
        top = view.rect["top"]
        bottom = view.rect["bottom"]
        if left < 0 or left > right:
            return False
        if right < 0 or right > view.screen_width:
            return False
        if top < 0 or top > bottom:
            return False
        if bottom < 0 or bottom > view.screen_height:
            return False
        return True


class GraphicalViewHasSpeakableTextCheck(Check):
    """
    Any graphical view (e.g. ImageView, ImageButton, Checkbox, etc.)
    should have a non-empty content description.
    """

    name = "graphical_view_has_content_desc_check"
    description = "Any graphical view (e.g. ImageView, ImageButton, Checkbox, etc.) \
                    should have a non-empty content description."

    def __init__(self) -> None:
        super().__init__(
            name=GraphicalViewHasSpeakableTextCheck.name,
            description=GraphicalViewHasSpeakableTextCheck.description,
        )

    def get_result_code(self, view: View) -> str:
        if check_utils.get_speakable_text_for_elem(view) == "":
            return ResultCode.MISSING_SPEAKABLE_TEXT
        return ResultCode.PASSED

    def is_eligible(self, view: View) -> bool:
        actionable = check_utils.should_focus_elem(view)
        return actionable and view.class_name in GRAPHICAL_VIEW_CLASSES


class EditableTextHasHintTextCheck(Check):
    """
    Any EditTexts and editable TextViews should have a non-empty hint text \
    and empty content description.
    """

    name = "editable_text_has_hint_text_check"
    description = "Any EditTexts and editable TextViews should have a non-empty hintText \
                    and empty content description."

    def __init__(self) -> None:
        super().__init__(
            name=EditableTextHasHintTextCheck.name,
            description=EditableTextHasHintTextCheck.description,
        )

    def get_result_code(self, view: View) -> str:
        if view.hint_text != "":
            if view.content_desc == "":
                result_code = ResultCode.PASSED
            else:
                result_code = ResultCode.HINT_TEXT_WITH_CONT_DESC
        else:
            if view.text != "":
                result_code = ResultCode.PASSED
            else:
                if view.content_desc == "":
                    result_code = ResultCode.MISSING_HINT_TEXT
                else:
                    result_code = ResultCode.MISSING_HINT_TEXT_WITH_CONT_DESC
        return result_code

    def is_eligible(self, view: View) -> bool:
        actionable = check_utils.should_focus_elem(view)
        class_name = view.class_name
        if not actionable:
            return False
        if class_name == "android.widget.EditText":
            return True
        if class_name == "android.widget.TextView" and view.is_editable:
            return True
        return False


class RedundantDescCheck(Check):
    """
    Speakable text should not contain redundant information about the view's type.
    """

    name = "redundant_desc_check"
    description = (
        "Speakable text should not contain redundant information about the view's type."
    )
    redundant_words = {"Button": ["button"], "CheckBox": ["checked"]}

    def __init__(self) -> None:
        super().__init__(
            name=RedundantDescCheck.name,
            description=RedundantDescCheck.description,
        )

    def get_result_code(self, view: View) -> str:
        for class_name, redun_words in RedundantDescCheck.redundant_words.items():
            if class_name not in view.class_name:
                continue
            for word in redun_words:
                if word in view.content_desc.lower():
                    return ResultCode.REDUNDANT_DESC
                if word in view.text.lower():
                    return ResultCode.REDUNDANT_DESC
        return ResultCode.PASSED

    def is_eligible(self, view: View) -> bool:
        actionable = check_utils.should_focus_elem(view)
        eligible_class = any(
            class_name in view.class_name
            for class_name in RedundantDescCheck.redundant_words.keys()
        )
        return actionable and eligible_class


class UninformativeLabelCheck(Check):
    """
    Any graphical view should not have an uninformative label.
    """

    name = "uninformative_label_check"
    description = "Any graphical view should not have an uninformative label."
    search_words = ["temp", "img", "text", "placeholder"]

    def __init__(self) -> None:
        super().__init__(
            name=UninformativeLabelCheck.name,
            description=UninformativeLabelCheck.description,
        )

    def get_result_code(self, view: View) -> str:
        speakable_text = check_utils.get_speakable_text_for_elem(view)
        for search_word in UninformativeLabelCheck.search_words:
            if search_word == speakable_text:
                return ResultCode.UNINFORMATIVE_DESC
        if len(speakable_text) == 1:
            return ResultCode.UNINFORMATIVE_DESC
        return ResultCode.PASSED

    def is_eligible(self, view: View) -> bool:
        actionable = check_utils.should_focus_elem(view)
        content_desc = view.content_desc
        class_name = view.class_name
        return (
            actionable and content_desc != "" and class_name in GRAPHICAL_VIEW_CLASSES
        )


class DuplicateSpeakableTextCheck(Check):
    """
    Any two views in a hierarchy should not have the same speakable text.
    """

    name = "duplicate_speakable_text_check"
    description = (
        "Any two views in a hierarchy should not have the same speakable text."
    )

    def __init__(self) -> None:
        super().__init__(
            name=DuplicateSpeakableTextCheck.name,
            description=DuplicateSpeakableTextCheck.description,
        )

    def run(self, view_hierarchy: ViewHierarchy) -> List[CheckResult]:
        self.text_to_view_map = self._get_text_to_view_map(view_hierarchy)
        return super().run(view_hierarchy)

    @staticmethod
    def _get_text_to_view_map(view_hierarchy: ViewHierarchy) -> Dict[str, List[View]]:
        text_to_view_map = defaultdict(list)
        for view in view_hierarchy.get_views():
            speakable_text = check_utils.get_speakable_text_for_elem(view)
            text_to_view_map[speakable_text].append(view)
        return text_to_view_map

    def get_result_code(self, view: View) -> str:
        speakable_text = check_utils.get_speakable_text_for_elem(view)
        if not speakable_text:
            return ResultCode.PASSED
        views_with_same_text = self.text_to_view_map[speakable_text]
        if len(views_with_same_text) == 1:
            return ResultCode.PASSED
        actionable = [
            view
            for view in views_with_same_text
            if check_utils.is_actionable_for_accessibility(view)
        ]
        if actionable:
            return ResultCode.CLICKABLE_SAME_SPEAKABLE_TEXT
        else:
            return ResultCode.NON_CLICKABLE_SAME_SPEAKABLE_TEXT

    def is_eligible(self, view: View) -> bool:
        actionable = check_utils.should_focus_elem(view)
        speakable_text = check_utils.get_speakable_text_for_elem(view)
        return actionable and speakable_text != ""
