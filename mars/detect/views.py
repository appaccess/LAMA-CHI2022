import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class View:
    bounds: str  # [x1,y1][x2,y2]
    class_name: str
    content_desc: str
    hint_text: str
    inherited_label: str
    is_accessibility_focused: bool
    is_checkable: bool
    is_checked: bool
    is_clickable: bool
    is_content_invalid: bool
    is_context_clickable: bool
    is_dismissable: bool
    is_editable: bool
    is_enabled: bool
    is_focusable: bool
    is_focused: bool
    is_important_for_accessibility: bool
    is_long_clickable: bool
    is_multi_line: bool
    is_password: bool
    is_screen_reader_focusable: bool
    is_scrollable: bool
    is_selected: bool
    is_showing_hint_text: bool
    is_visible_to_user: bool
    package_name: str
    pane_title: str
    rect: Dict[str, int]
    resource_id: str
    screen_height: int
    screen_width: int
    text: str
    tooltip_text: str
    parent: Optional["View"]
    path: str
    children: List["View"]
    label: Optional[str] = ""
    uuid: Optional[str] = ""


class ViewHierarchy:
    def __init__(self, filepath: str, uuid: Optional[str] = "") -> None:
        if uuid:
            self.uuid = uuid
        else:
            self.uuid = os.path.splitext(os.path.basename(filepath))[0]
        with open(filepath, "r") as f:
            data = json.load(f)
        self.root = self._create_view_hierarchy(node=data, parent=None, path=[])

    def _create_view_hierarchy(self, node: Any, parent: Optional[View], path: List[str]) -> View:
        children = []
        for i, child in enumerate(node["children"]):
            new_path = list(path)
            new_path.append(str(i))
            child_view = self._create_view_hierarchy(node=child, parent=None, path=new_path)
            children.append(child_view)
        path_as_str = ",".join(path)
        view = View(
            bounds=node["bounds"],
            class_name=node["className"],
            content_desc=node["contentDesc"],
            hint_text=node["hintText"],
            inherited_label=node["inheritedLabel"],
            is_accessibility_focused=node["isAccessibilityFocused"],
            is_checkable=node["isCheckable"],
            is_checked=node["isChecked"],
            is_clickable=node["isClickable"],
            is_content_invalid=node["isContentInvalid"],
            is_context_clickable=node["isContextClickable"],
            is_dismissable=node["isDismissable"],
            is_editable=node["isEditable"],
            is_enabled=node["isEnabled"],
            is_focusable=node["isFocusable"],
            is_focused=node["isFocused"],
            is_important_for_accessibility=node["isImportantForAccessibility"],
            is_long_clickable=node["isLongClickable"],
            is_multi_line=node["isMultiLine"],
            is_password=node["isPassword"],
            is_screen_reader_focusable=node["isScreenReaderFocusable"],
            is_scrollable=node["isScrollable"],
            is_selected=node["isSelected"],
            is_showing_hint_text=node["isShowingHintText"],
            is_visible_to_user=node["isVisibleToUser"],
            package_name=node["packageName"],
            pane_title=node["paneTitle"],
            rect=node["rect"],
            resource_id=node["resourceId"],
            screen_height=node["screenHeight"],
            screen_width=node["screenWidth"],
            text=node["text"],
            tooltip_text=node["tooltipText"],
            parent=parent,
            path=path_as_str,
            children=children,
            label="__".join([node["className"], node["resourceId"]]),
            uuid=self.uuid,
        )
        for child_view in children:
            child_view.parent = view
        return view

    def get_views(self) -> Iterator[View]:
        queue = [self.root]
        while queue:
            cur_view = queue.pop(0)
            for child_view in cur_view.children:
                queue.append(child_view)
            yield cur_view

    def print_simple(self) -> None:
        def print_simple_helper(view, depth):
            print(f'{"--" * depth}[{view.class_name}, {view.resource_id}]')
            for child_view in view.children:
                print_simple_helper(child_view, depth + 1)

        print_simple_helper(self.root, 0)
