import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_flutter/lucide_flutter.dart';
import 'package:path_provider/path_provider.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/network/dio_factory.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/utils/platform_paths.dart';
import '../../../core/utils/ui_message.dart';
import '../../../core/widgets/primary_button.dart';
import '../../../core/widgets/toast_exception.dart';
import '../../platforms/presentation/platforms_controller.dart';
import '../domain/gallery_repository.dart';
import '../domain/image_record.dart';
import 'metadata_sheet.dart';

/// Pinned review bar: **Approve first**, overflow for the rest (05 §2.6).
///
/// * Approve is disabled + dimmed while [offline]; when the record is
///   already approved the button becomes **Reprocess** (reset-stage).
/// * Overflow (≥44 dp, semantics "More actions"): Download · Mark
///   used/unused · Reset stage · Delete — the last two behind confirm
///   dialogs, Delete rust-toned destructive.
/// * Every network failure reports through [onConnectivityChanged] (`false`
///   on [NetworkException]) so the screen can pin the offline note and
///   disable everything, per 05's "cached metadata stays viewable".
class ReviewActionBar extends ConsumerStatefulWidget {
  const ReviewActionBar({
    super.key,
    required this.record,
    required this.offline,
    required this.onApproved,
    required this.onRecordChanged,
    required this.onDeleted,
    required this.onConnectivityChanged,
  });

  /// Record backing the buttons (status drives Approve ↔ Reprocess).
  final ImageRecord record;

  /// True while the screen knows the network is down — all actions disabled.
  final bool offline;

  /// Approve/Reprocess succeeded — screen shows the stamp + invalidates.
  final VoidCallback onApproved;

  /// Mark-used / Reset succeeded — screen refetches the record.
  final VoidCallback onRecordChanged;

  /// Delete succeeded — screen navigates back to the grid.
  final VoidCallback onDeleted;

  /// `true` after any successful network action, `false` on
  /// [NetworkException] — screen maps it to [ReviewActionBar.offline].
  final ValueChanged<bool> onConnectivityChanged;

  @override
  ConsumerState<ReviewActionBar> createState() => _ReviewActionBarState();
}

enum _MenuAction { download, markUsed, reset, delete }

class _ReviewActionBarState extends ConsumerState<ReviewActionBar> {
  bool _busy = false;

  bool get _isReprocess => isApprovedStatus(widget.record.status);

  String get _filename => widget.record.filename;

  /// Shared success/failure runner: toast, connectivity, callback.
  Future<void> _run(
    String successMessage,
    Future<void> Function() action, {
    VoidCallback? onSuccess,
  }) async {
    try {
      await action();
      widget.onConnectivityChanged(true);
      if (mounted) {
        showAppToast(context, successMessage, tone: ToastTone.success);
      }
      onSuccess?.call();
    } catch (error) {
      if (error is NetworkException) {
        widget.onConnectivityChanged(false);
      }
      if (mounted) {
        showAppToast(context, _messageFor(error), tone: ToastTone.error);
      }
    }
  }

  String _messageFor(Object error) => error is AppException
      ? uiMessageFor(error)
      : 'Something went wrong.';

  Future<void> _approve() async {
    if (widget.offline || _busy) {
      return;
    }
    await HapticFeedback.mediumImpact();
    if (!mounted) {
      return;
    }
    setState(() => _busy = true);
    final GalleryRepository repo = ref.read(galleryRepositoryProvider);
    if (_isReprocess) {
      await _run(
        'Stage reset · $_filename',
        () => repo.resetStage(widget.record.id),
        onSuccess: widget.onRecordChanged,
      );
    } else {
      await _run(
        'Approved · $_filename',
        () => repo.approve(widget.record.id),
        onSuccess: widget.onApproved,
      );
    }
    if (mounted) {
      setState(() => _busy = false);
    }
  }

  Future<void> _showMenu() async {
    final RenderBox button = context.findRenderObject()! as RenderBox;
    final RenderBox overlay =
        Overlay.of(context).context.findRenderObject()! as RenderBox;
    final RelativeRect position = RelativeRect.fromRect(
      button.localToGlobal(Offset.zero) & button.size,
      Offset.zero & overlay.size,
    );
    final _MenuAction? action = await showMenu<_MenuAction>(
      context: context,
      position: position,
      items: <PopupMenuEntry<_MenuAction>>[
        PopupMenuItem<_MenuAction>(
          value: _MenuAction.download,
          child: _MenuItem(icon: LucideIcons.download, label: 'Download'),
        ),
        PopupMenuItem<_MenuAction>(
          value: _MenuAction.markUsed,
          child: _MenuItem(
            icon: widget.record.used == true
                ? LucideIcons.circleX
                : LucideIcons.circleCheck,
            label: widget.record.used == true ? 'Mark unused' : 'Mark used',
          ),
        ),
        PopupMenuItem<_MenuAction>(
          value: _MenuAction.reset,
          child: _MenuItem(icon: LucideIcons.rotateCcw, label: 'Reset stage'),
        ),
        PopupMenuItem<_MenuAction>(
          value: _MenuAction.delete,
          child: _MenuItem(
            icon: LucideIcons.trash2,
            label: 'Delete',
            color: AppColors.rust400,
          ),
        ),
      ],
    );
    if (action == null || !mounted) {
      return;
    }
    switch (action) {
      case _MenuAction.download:
        await _download();
      case _MenuAction.markUsed:
        await _markUsed();
      case _MenuAction.reset:
        await _reset();
      case _MenuAction.delete:
        await _delete();
    }
  }

  Future<void> _download() async {
    try {
      final Dio dio = ref.read(dioProvider);
      final String platformId = ref.read(activePlatformIdProvider);
      final Response<List<int>> response = await dio.get<List<int>>(
        platformPath(platformId, 'records/${widget.record.id}/file'),
        options: Options(responseType: ResponseType.bytes),
      );
      final List<int>? bytes = response.data;
      if (bytes == null || bytes.isEmpty) {
        if (mounted) {
          showAppToast(context, 'Download returned no data.', tone: ToastTone.error);
        }
        return;
      }
      final Directory docs = await getApplicationDocumentsDirectory();
      final Directory dir = Directory('${docs.path}/downloads');
      if (!dir.existsSync()) {
        dir.createSync(recursive: true);
      }
      final File file = _uniqueFile(dir, _sanitize(_filename));
      await file.writeAsBytes(bytes, flush: true);
      widget.onConnectivityChanged(true);
      if (mounted) {
        showAppToast(context, 'Saved to ${file.path}', tone: ToastTone.success);
      }
    } catch (error) {
      if (error is NetworkException) {
        widget.onConnectivityChanged(false);
      }
      if (mounted) {
        showAppToast(context, _messageFor(error), tone: ToastTone.error);
      }
    }
  }

  Future<void> _markUsed() async {
    final bool target = !(widget.record.used ?? false);
    await _run(
      target ? 'Marked used · $_filename' : 'Marked unused · $_filename',
      () => ref
          .read(galleryRepositoryProvider)
          .markUsed(widget.record.id, used: target),
      onSuccess: widget.onRecordChanged,
    );
  }

  Future<void> _reset() async {
    final bool? confirmed = await _confirm(
      title: 'Reset this stage?',
      message:
          'Acceptance metadata for $_filename is cleared and the record '
          'returns to Pending.',
      confirmLabel: 'Reset',
    );
    if (confirmed != true || !mounted) {
      return;
    }
    await _run(
      'Stage reset · $_filename',
      () => ref.read(galleryRepositoryProvider).resetStage(widget.record.id),
      onSuccess: widget.onRecordChanged,
    );
  }

  Future<void> _delete() async {
    final bool? confirmed = await _confirm(
      title: 'Delete this record?',
      message: '$_filename and its thumbnails are removed from the studio. '
          'This cannot be undone.',
      confirmLabel: 'Delete',
      destructive: true,
    );
    if (confirmed != true || !mounted) {
      return;
    }
    await _run(
      'Deleted · $_filename',
      () => ref.read(galleryRepositoryProvider).deleteRecord(widget.record.id),
      onSuccess: widget.onDeleted,
    );
  }

  Future<bool?> _confirm({
    required String title,
    required String message,
    required String confirmLabel,
    bool destructive = false,
  }) {
    return showDialog<bool>(
      context: context,
      builder: (BuildContext ctx) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(
              confirmLabel,
              style: TextStyle(
                color: destructive ? AppColors.rust400 : AppColors.olive400,
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// `downloads/` under the app documents dir; never overwrites an
  /// existing file — `name (1).ext`, `name (2).ext`, …
  File _uniqueFile(Directory dir, String name) {
    final int dot = name.lastIndexOf('.');
    final String stem = dot > 0 ? name.substring(0, dot) : name;
    final String ext = dot > 0 ? name.substring(dot) : '';
    File file = File('${dir.path}/$name');
    int counter = 1;
    while (file.existsSync()) {
      file = File('${dir.path}/$stem ($counter)$ext');
      counter += 1;
    }
    return file;
  }

  String _sanitize(String name) {
    final String cleaned = name.replaceAll(RegExp(r'[<>:"/\\|?*]'), '_').trim();
    return cleaned.isEmpty ? 'image.jpg' : cleaned;
  }

  @override
  Widget build(BuildContext context) {
    final bool disabled = widget.offline;
    return SafeArea(
      top: false,
      child: DecoratedBox(
        decoration: const BoxDecoration(
          color: AppColors.parchment50,
          border: Border(top: BorderSide(color: AppColors.parchment400)),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.lg,
            AppSpacing.sm,
            AppSpacing.md,
            AppSpacing.sm,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              if (disabled) const _OfflineNote(),
              Row(
                children: <Widget>[
                  Expanded(child: _approveButton(disabled)),
                  const SizedBox(width: AppSpacing.sm),
                  _overflowButton(disabled),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _approveButton(bool disabled) {
    final Widget button = PrimaryButton(
      label: _isReprocess ? 'Reprocess' : 'Approve',
      expanded: true,
      loading: _busy,
      // Disabled state dims instead of PrimaryButton's spinner-on-null.
      onPressed: disabled ? () {} : _approve,
    );
    if (!disabled) {
      return button;
    }
    return Opacity(
      opacity: 0.5,
      child: IgnorePointer(child: button),
    );
  }

  Widget _overflowButton(bool disabled) {
    final Widget button = IconButton(
      onPressed: disabled ? () {} : _showMenu,
      tooltip: 'More actions',
      icon: const Icon(LucideIcons.ellipsisVertical),
      constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
    );
    if (!disabled) {
      return button;
    }
    return Opacity(
      opacity: 0.5,
      child: IgnorePointer(child: button),
    );
  }
}

/// Small offline strip pinned above the buttons (05: approve disabled
/// with a banner note; cached metadata stays viewable).
class _OfflineNote extends StatelessWidget {
  const _OfflineNote();

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        children: <Widget>[
          const Icon(LucideIcons.wifiOff, size: 14, color: AppColors.rust400),
          const SizedBox(width: AppSpacing.xs),
          Expanded(
            child: Text(
              'Offline — actions disabled. Metadata below is cached.',
              style: textTheme.bodySmall?.copyWith(color: AppColors.rust400),
            ),
          ),
        ],
      ),
    );
  }
}

/// Icon + label row for the overflow menu items.
class _MenuItem extends StatelessWidget {
  const _MenuItem({required this.icon, required this.label, this.color});

  final IconData icon;
  final String label;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Icon(icon, size: 18, color: color),
        const SizedBox(width: AppSpacing.sm),
        Text(label, style: color == null ? null : TextStyle(color: color)),
      ],
    );
  }
}
