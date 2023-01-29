"""
Implements util functions found in ViewHierarchyElementUtils.java.
Reference at https://github.com/google/Accessibility-Test-Framework-for-Android/blob/master/src/main/java/com/google/android/apps/common/testing/accessibility/framework/ViewHierarchyElementUtils.java
"""
from typing import Optional

from .views import View


def get_speakable_text_for_elem(elem: View) -> str:
    if not elem.is_important_for_accessibility:
        return ""

    if elem.inherited_label:
        return elem.inherited_label

    if elem.content_desc:
        return elem.content_desc

    parts = []
    if elem.text:
        parts.append(elem.text)
    if elem.is_checkable:
        if elem.is_checked:
            parts.append("Checked")
        else:
            parts.append("Not checked")

    for child in elem.children:
        if child.is_visible_to_user and not is_actionable_for_accessibility(child):
            child_text = get_speakable_text_for_elem(child)
            if child_text:
                parts.append(child_text)

    return " ".join(parts)


def should_focus_elem(elem: View) -> bool:
    if not elem.is_visible_to_user:
        return False
    if is_accessibility_focusable(elem):
        if not has_any_important_descendant(elem):
            return True
        if is_speaking_elem(elem):
            return True
        return False
    return (
        has_text(elem) and elem.is_important_for_accessibility and not has_focusable_ancestor(elem)
    )


def is_actionable_for_accessibility(elem: View) -> bool:
    return elem.is_clickable or elem.is_long_clickable or elem.is_focusable


def has_focusable_ancestor(elem: View) -> bool:
    focusable_parent = get_important_for_accessibility_ancestor(elem)
    if not focusable_parent:
        return False
    if is_accessibility_focusable(focusable_parent):
        return True
    return has_focusable_ancestor(focusable_parent)


def is_accessibility_focusable(elem: View) -> bool:
    if not elem.is_visible_to_user:
        return False
    if not elem.is_important_for_accessibility:
        return False
    if is_actionable_for_accessibility(elem):
        return True

    return is_child_of_scrollable_container(elem) and is_speaking_elem(elem)


def is_child_of_scrollable_container(elem: View) -> bool:
    parent = get_important_for_accessibility_ancestor(elem)
    if not parent:
        return False
    if parent.is_scrollable:
        return True
    if parent.class_name == "android.widget.Spinner":
        return False
    return parent.class_name in [
        "android.widget.AdapterView",
        "android.widget.ScrollView",
        "android.widget.HorizontalScrollView",
    ]


def is_speaking_elem(elem: View) -> bool:
    nonfocusable_speaking_children = has_nonfocusable_speaking_children(elem)
    return has_text(elem) or elem.is_checkable or nonfocusable_speaking_children


def has_nonfocusable_speaking_children(elem: View) -> bool:
    for child in elem.children:
        if not child.is_visible_to_user or is_accessibility_focusable(child):
            continue

        if child.is_important_for_accessibility and (has_text(child) or child.is_checkable):
            return True
        if has_nonfocusable_speaking_children(child):
            return True
    return False


def has_text(elem: View) -> bool:
    return elem.text != "" or elem.content_desc != ""


def get_important_for_accessibility_ancestor(elem: View) -> Optional[View]:
    parent_elem = elem.parent
    while parent_elem and not parent_elem.is_important_for_accessibility:
        parent_elem = parent_elem.parent
    return parent_elem


def has_any_important_descendant(elem: View) -> bool:
    for child in elem.children:
        if child.is_important_for_accessibility:
            return True
        if child.children:
            if has_any_important_descendant(child):
                return True
    return False


def is_accessibility_focusable_all(elem: View) -> bool:
    return elem.is_important_for_accessibility and is_actionable_for_accessibility(elem)
