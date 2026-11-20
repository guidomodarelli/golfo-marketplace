#!/usr/bin/env python3
"""Merge managed Agent Ready settings while preserving project customizations."""

import argparse
import json
import sys


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-nested-template-match",
        action="store_true",
        help="Allow a managed object or list to match within a nested managed value.",
    )
    parser.add_argument("template_path")
    parser.add_argument("settings_path")
    return parser.parse_args()


def has_custom_keys(current, expected):
    if isinstance(current, dict) and isinstance(expected, dict):
        return any(
            key not in expected or has_custom_keys(value, expected[key])
            for key, value in current.items()
        )
    if isinstance(current, list) and isinstance(expected, list):
        return any(entry not in expected for entry in current)
    return False


def matches_managed_template(current, expected, allow_nested_template_match):
    if isinstance(current, dict) and isinstance(expected, dict):
        if all(
            key in current
            and matches_managed_template(
                current[key], value, allow_nested_template_match
            )
            for key, value in expected.items()
            # Progress copy can change without creating a second managed hook.
            if not (
                key == "statusMessage"
                and expected.get("type") == "command"
                and "command" in expected
            )
        ):
            return True
        if allow_nested_template_match:
            return any(
                key in current
                and isinstance(value, (dict, list))
                and matches_managed_template(
                    current[key], value, allow_nested_template_match
                )
                for key, value in expected.items()
            )
        return False
    if isinstance(current, list) and isinstance(expected, list):
        current_index = 0
        for expected_entry in expected:
            matching_index = next(
                (
                    index
                    for index in range(current_index, len(current))
                    if matches_managed_template(
                        current[index], expected_entry, allow_nested_template_match
                    )
                ),
                None,
            )
            if matching_index is None:
                return False
            current_index = matching_index + 1
        return True
    return current == expected


def is_managed_duplicate(
    current_entry, expected_entry, merged_entry, allow_nested_template_match
):
    """Detect a repeated managed entry that carries no project customization."""
    return matches_managed_template(
        current_entry, expected_entry, allow_nested_template_match
    ) and (
        merge_managed_template(
            current_entry, expected_entry, allow_nested_template_match
        )
        == merged_entry
    )


def merge_managed_template(current, expected, allow_nested_template_match):
    if isinstance(current, dict) and isinstance(expected, dict):
        merged = dict(current)
        for key, value in expected.items():
            if key in current:
                merged[key] = merge_managed_template(
                    current[key], value, allow_nested_template_match
                )
            else:
                merged[key] = value
        return merged
    if isinstance(current, list) and isinstance(expected, list):
        remaining_current = list(current)
        merged = []
        for expected_entry in expected:
            matching_index = next(
                (
                    index
                    for index, current_entry in enumerate(remaining_current)
                    if matches_managed_template(
                        current_entry, expected_entry, allow_nested_template_match
                    )
                ),
                None,
            )
            if matching_index is None:
                merged.append(expected_entry)
                continue
            merged.extend(remaining_current[:matching_index])
            merged_entry = merge_managed_template(
                remaining_current[matching_index],
                expected_entry,
                allow_nested_template_match,
            )
            merged.append(merged_entry)
            remaining_current = [
                current_entry
                for current_entry in remaining_current[matching_index + 1 :]
                if not is_managed_duplicate(
                    current_entry,
                    expected_entry,
                    merged_entry,
                    allow_nested_template_match,
                )
            ]
        return merged + remaining_current
    return expected


def main():
    # Windows stdout defaults to CRLF and the locale code page; the generated JSON is LF UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    arguments = parse_arguments()
    try:
        with open(arguments.template_path, encoding="utf-8") as template_file:
            template = json.load(template_file)
        with open(arguments.settings_path, encoding="utf-8") as settings_file:
            settings = json.load(settings_file)
    except (OSError, json.JSONDecodeError):
        return 1

    allow_nested_template_match = arguments.allow_nested_template_match
    if not has_custom_keys(settings, template):
        return 10

    json.dump(
        merge_managed_template(settings, template, allow_nested_template_match),
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
