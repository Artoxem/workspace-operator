"""Declarative routing table: handler name -> function and argument mapping.

Each row says which function in :mod:`workspace_operator.server` implements a
handler and how its positional arguments are read from the tool arguments:

    P("key")                      -> arguments.get("key")
    P("key", default=5)           -> arguments.get("key", 5)
    P("key", fallback={})         -> arguments.get("key") or {}
    "_on_bulk_finish"             -> a callback supplied by the server

The functions are looked up by *name* in the server module at call time, so
tests that patch a handler there keep working. ``tests/test_handler_dispatch.py``
pins what every handler receives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union

_MISSING: Any = object()


@dataclass(frozen=True)
class P:
    """One positional handler argument read from the tool arguments."""

    key: str
    default: Any = None
    fallback: Any = _MISSING

    def read(self, arguments: Mapping[str, Any]) -> Any:
        value = arguments.get(self.key, self.default)
        if self.fallback is not _MISSING and not value:
            # `a.get(key) or fallback`: any falsy value is replaced.
            return _copy(self.fallback)
        return value


def _copy(value: Any) -> Any:
    """Fresh container per call so handlers cannot share a mutable default."""
    if isinstance(value, dict):
        return {}
    if isinstance(value, list):
        return []
    return value


Arg = Union[P, str]  # a string names a callback slot

#: handler name -> (function name in workspace_operator.server, arguments)
ROUTES: Dict[str, Tuple[str, Tuple[Arg, ...]]] = {
    'bulk_plan': ('bulk_plan_handler', (P('domain', default='drive'), P('action'), P('selector', fallback={}), P('options', fallback={}), P('allow_large', default=False), P('sample', default=5),)),
    'bulk_status': ('bulk_status_handler', (P('job_id'),)),
    'bulk_cancel': ('bulk_cancel_handler', (P('job_id'),)),
    'bulk_result': ('bulk_result_handler', (P('job_id'), P('offset', default=0), P('limit', default=50),)),
    'bulk_list': ('bulk_list_handler', (P('limit', default=10),)),
    'bulk_undo': ('bulk_undo_handler', (P('job_id'), P('confirm', default=False), '_on_undo_finish',)),
    'tasks_list_lists': ('tasks_list_lists_handler', ()),
    'tasks_list': ('tasks_list_handler', (P('tasklist_id', default='@default'), P('show_completed', default=False), P('max_results', default=50),)),
    'tasks_create': ('tasks_create_handler', (P('title'), P('notes'), P('due'), P('tasklist_id', default='@default'),)),
    'tasks_complete': ('tasks_complete_handler', (P('task_id'), P('tasklist_id', default='@default'),)),
    'forms_create': ('forms_create_handler', (P('title'), P('description'),)),
    'forms_add_questions': ('forms_add_questions_handler', (P('form_id'), P('questions', fallback=[]),)),
    'forms_get': ('forms_get_handler', (P('form_id'),)),
    'forms_list_responses': ('forms_list_responses_handler', (P('form_id'), P('max_results', default=50),)),
    'postmaster_list_domains': ('postmaster_list_domains_handler', ()),
    'postmaster_traffic_stats': ('postmaster_traffic_stats_handler', (P('domain'), P('days', default=7),)),
    'workspace_search': ('workspace_search_handler', (P('query'), P('sources'), P('limit', default=10), P('calendar_days_back', default=30), P('calendar_days_ahead', default=180),)),
    'drive_export': ('drive_export_handler', (P('file_id'), P('format'), P('save_to'), P('overwrite', default=False),)),
    'script_run_function': ('script_run_function_handler', (P('script_id'), P('function_name'), P('parameters'), P('dev_mode', default=True),)),
    'read_sheet': ('read_sheet_handler', (P('spreadsheet_id'), P('range_name'),)),
    'append_row': ('append_row_handler', (P('spreadsheet_id'), P('range_name'), P('values'),)),
    'update_sheet': ('update_sheet_handler', (P('spreadsheet_id'), P('range_name'), P('values'),)),
    'create_script_project': ('create_script_project_handler', (P('title'), P('parent_id'),)),
    'get_script_content': ('get_script_content_handler', (P('script_id'),)),
    'prepare_script_update': ('prepare_script_update_handler', (P('script_id'), P('files'),)),
    'execute_operation': ('execute_operation_handler', (P('operation_id'),)),
    'cancel_operation': ('cancel_operation_handler', (P('operation_id'),)),
    'restore_script_backup': ('restore_script_backup_handler', (P('backup_path'),)),
    'read_doc': ('read_doc_handler', (P('document_id'),)),
    'create_doc': ('create_doc_handler', (P('title'),)),
    'append_to_doc': ('append_to_doc_handler', (P('document_id'), P('text'),)),
    'create_spreadsheet': ('create_spreadsheet_handler', (P('title'),)),
    'add_sheet': ('add_sheet_handler', (P('spreadsheet_id'), P('title'),)),
    'clear_range': ('clear_range_handler', (P('spreadsheet_id'), P('range_name'), P('confirm', default=False),)),
    'sheet_create_filter_view': ('sheet_create_filter_view_handler', (P('spreadsheet_id'), P('sheet_id'), P('title'), P('start_row', default=0), P('end_row'), P('start_col', default=0), P('end_col'),)),
    'sheet_export_csv': ('sheet_export_csv_handler', (P('spreadsheet_id'), P('range_name'), P('max_rows', default=5000),)),
    'sheet_find_replace': ('sheet_find_replace_handler', (P('spreadsheet_id'), P('range_name'), P('find_text'), P('replace_text'), P('dry_run', default=True), P('match_case', default=False),)),
    'sheet_create_named_range': ('sheet_create_named_range_handler', (P('spreadsheet_id'), P('name'), P('sheet_id'), P('start_row'), P('end_row'), P('start_col'), P('end_col'),)),
    'sheet_format': ('format_sheet_handler', (P('spreadsheet_id'), P('sheet_name'), P('range'), P('bold'), P('italic'), P('font_size'), P('number_format'), P('background_color'), P('text_color'), P('horizontal_alignment'), P('wrap'), P('column_width'), P('row_height'), P('freeze_rows'), P('freeze_cols'),)),
    'get_spreadsheet_meta': ('get_spreadsheet_meta_handler', (P('spreadsheet_id'),)),
    'send_email': ('send_email_handler', (P('to'), P('subject'), P('body_text'), P('draft_mode', default=True),)),
    'send_draft': ('send_draft_handler', (P('draft_id'),)),
    'get_gmail_profile': ('get_gmail_profile_handler', ()),
    'create_draft': ('create_draft_handler', (P('to'), P('subject'), P('body_text'),)),
    'list_emails': ('list_emails_handler', (P('max_results', default=10), P('query'),)),
    'calendar_update_event': ('calendar_update_event_handler', (P('event_id'), P('calendar_id', default='primary'), P('summary'), P('start_time'), P('end_time'), P('description'), P('location'), P('attendees'), P('send_updates', default='none'),)),
    'calendar_delete_event': ('calendar_delete_event_handler', (P('event_id'), P('calendar_id', default='primary'), P('confirm', default=False), P('send_updates', default='none'),)),
    'calendar_respond_to_invite': ('calendar_respond_to_invite_handler', (P('event_id'), P('response'), P('calendar_id', default='primary'), P('confirm', default=False), P('send_updates', default='all'),)),
    'digest': ('digest_handler', (P('sources'), P('since_hours', default=24), P('limit', default=10), P('output', default='text'), P('doc_title'),)),
    'compare_tables': ('compare_tables_handler', (P('spreadsheet_id'), P('range_a'), P('range_b'), P('other_spreadsheet_id'), P('key_column', default='1'), P('header', default=True), P('output', default='text'), P('doc_title'),)),
    'gmail_get_thread': ('gmail_get_thread_handler', (P('thread_id'), P('message_id'), P('include_body', default=False),)),
    'gmail_get_attachment': ('gmail_get_attachment_handler', (P('message_id'), P('attachment_id'), P('filename'), P('save_to'), P('overwrite', default=False),)),
    'gmail_reply': ('gmail_reply_handler', (P('message_id'), P('body_text'), P('reply_all', default=False), P('draft_mode', default=True),)),
    'read_email': ('read_email_handler', (P('message_id'),)),
    'delete_email': ('delete_email_handler', (P('message_id'), P('confirm', default=False),)),
    'gmail_search_and_summarize': ('gmail_search_and_summarize_handler', (P('query'), P('max_results', default=50),)),
    'gmail_archive': ('gmail_archive_handler', (P('message_id'), P('confirm', default=False),)),
    'gmail_label_apply': ('gmail_label_apply_handler', (P('message_ids'), P('label_name'), P('dry_run', default=True), P('create_if_missing', default=True),)),
    'list_events': ('list_events_handler', (P('calendar_id', default='primary'), P('max_results', default=10),)),
    'calendar_create_meeting': ('calendar_create_meeting_handler', (P('summary'), P('start_time'), P('end_time'), P('attendees'), P('description', default=''), P('location', default=''), P('confirm', default=False),)),
    'create_folder': ('create_folder_handler', (P('name'), P('parent_id'),)),
    'share_file': ('share_file_handler', (P('file_id'), P('role'), P('type', default='user'), P('email_address'), P('allow_public', default=False),)),
    'drive_search_advanced': ('drive_search_advanced_handler', (P('query'), P('limit', default=50),)),
    'drive_list_permissions': ('drive_list_permissions_handler', (P('file_id'),)),
    'drive_revoke_public': ('drive_revoke_public_handler', (P('file_id'), P('confirm', default=False),)),
    'drive_copy_file': ('drive_copy_file_handler', (P('file_id'), P('name'), P('parent_id'),)),
    'drive_get_metadata': ('get_metadata_handler', (P('file_id'),)),
    'drive_rename_file': ('rename_file_handler', (P('file_id'), P('name'),)),
    'drive_delete_file': ('delete_file_handler', (P('file_id'), P('confirm', default=False),)),
    'drive_restore_file': ('restore_file_handler', (P('file_id'),)),
    'drive_remove_permission': ('remove_permission_handler', (P('file_id'), P('permission_id'), P('confirm', default=False),)),
    'doc_replace_text': ('replace_text_handler', (P('document_id'), P('find'), P('replace'), P('match_case', default=False), P('confirm', default=False),)),
    'sheet_conditional_format': ('conditional_format_handler', (P('spreadsheet_id'), P('range'), P('condition'), P('value'), P('value2'), P('background_color', default='#FFF2CC'), P('text_color'), P('sheet_name'),)),
    'sheet_add_chart': ('add_chart_handler', (P('spreadsheet_id'), P('range'), P('chart_type', default='COLUMN'), P('title'), P('sheet_name'), P('header', default=True), P('anchor_row', default=0), P('anchor_col', default=0), P('width', default=600), P('height', default=371),)),
    'sheet_delete_sheet': ('delete_sheet_handler', (P('spreadsheet_id'), P('sheet_name'), P('confirm', default=False),)),
    'sheet_insert_rows': ('insert_rows_handler', (P('spreadsheet_id'), P('sheet_name'), P('start_row', default=1), P('count', default=1),)),
    'sheet_delete_rows': ('delete_rows_handler', (P('spreadsheet_id'), P('sheet_name'), P('start_row', default=1), P('count', default=1), P('confirm', default=False),)),
    'sheet_merge_cells': ('merge_cells_handler', (P('spreadsheet_id'), P('range'), P('merge_type', default='MERGE_ALL'), P('sheet_name'),)),
    'gmail_list_labels': ('list_labels_handler', ()),
    'gmail_create_label': ('create_label_handler', (P('name'), P('label_list_visibility', default='labelShow'), P('message_list_visibility', default='show'),)),
    'sheet_insert_columns': ('insert_columns_handler', (P('spreadsheet_id'), P('sheet_name'), P('start_column', default=1), P('count', default=1),)),
    'sheet_delete_columns': ('delete_columns_handler', (P('spreadsheet_id'), P('sheet_name'), P('start_column', default=1), P('count', default=1), P('confirm', default=False),)),
    'sheet_sort_range': ('sort_range_handler', (P('spreadsheet_id'), P('range'), P('column', default=1), P('ascending', default=True), P('sheet_name'),)),
    'docs_insert_image': ('insert_image_handler', (P('document_id'), P('image_url'), P('width'), P('height'),)),
    'calendar_list_calendars': ('list_calendars_handler', ()),
    'gmail_send_with_attachments': ('send_with_attachments_handler', (P('to'), P('subject'), P('body_text'), P('attachments', fallback=[]), P('draft_mode', default=True),)),
    'script_list_deployments': ('list_deployments_handler', (P('script_id'),)),
    'sheet_add_pivot_table': ('add_pivot_table_handler', (P('spreadsheet_id'), P('source_range'), P('rows', fallback=[]), P('values', fallback=[]), P('columns', fallback=[]), P('aggregation', default='SUM'), P('target_sheet_name', default='Pivot'), P('sheet_name'),)),
    'docs_format_text': ('format_text_handler', (P('document_id'), P('find'), P('bold', default=False), P('italic', default=False), P('font_size', default=0), P('heading', default=''), P('match_case', default=False), P('confirm', default=False),)),
    'gmail_list_drafts': ('list_drafts_handler', (P('limit', default=10),)),
    'gmail_delete_draft': ('delete_draft_tool', (P('draft_id'), P('confirm', default=False),)),
    'calendar_move_event': ('move_event_handler', (P('event_id'), P('destination_calendar_id'), P('calendar_id', default='primary'),)),
    'script_create_deployment': ('create_deployment_handler', (P('script_id'), P('description', default=''), P('version_number', default=0),)),
    'sheet_set_data_validation': ('set_data_validation_handler', (P('spreadsheet_id'), P('range'), P('values'), P('minimum'), P('maximum'), P('strict', default=True), P('input_message', default=''), P('sheet_name'),)),
    'sheet_protect_range': ('protect_range_handler', (P('spreadsheet_id'), P('range'), P('description', default=''), P('warning_only', default=True), P('editors'), P('sheet_name'),)),
    'sheet_set_borders': ('set_borders_handler', (P('spreadsheet_id'), P('range'), P('style', default='SOLID'), P('color', default='#000000'), P('sides'), P('sheet_name'),)),
    'gmail_list_filters': ('list_filters_handler', ()),
    'gmail_create_filter': ('create_filter_handler', (P('from_address', default=''), P('subject', default=''), P('query', default=''), P('add_labels'), P('remove_labels'),)),
    'gmail_update_draft': ('update_draft_handler', (P('draft_id'), P('to'), P('subject'), P('body_text'),)),
    'calendar_set_event_color': ('set_event_color_handler', (P('event_id'), P('color_id'), P('calendar_id', default='primary'),)),
    'script_update_deployment': ('update_deployment_handler', (P('script_id'), P('deployment_id'), P('version_number', default=0), P('description', default=''),)),
}


def build_handlers(
    server_module: Any,
    config: Any,
    logger: Any,
    callbacks: Optional[Mapping[str, Callable[..., Any]]] = None,
) -> Dict[str, Callable[[Mapping[str, Any]], Any]]:
    """Return ``{handler name: callable(arguments)}`` for every route.

    ``server_module`` is resolved lazily on each call (``getattr``), so a patched
    handler is honoured.
    """
    callbacks = dict(callbacks or {})

    def make(function_name: str, params: Tuple[Arg, ...]) -> Callable[[Mapping[str, Any]], Any]:
        def call(arguments: Mapping[str, Any]) -> Any:
            function = getattr(server_module, function_name)
            values = [
                callbacks[param] if isinstance(param, str) else param.read(arguments)
                for param in params
            ]
            return function(config, logger, *values)

        return call

    return {name: make(function, params) for name, (function, params) in ROUTES.items()}
