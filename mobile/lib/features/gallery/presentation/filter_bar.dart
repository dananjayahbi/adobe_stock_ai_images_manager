import 'dart:async';

import 'package:flutter/material.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/status_chip.dart';
import '../domain/gallery_group.dart';
import '../domain/gallery_query.dart';

/// Stage chips — labels and values mirrored byte-for-byte from
/// `frontend-new/src/components/gallery/FilterBar.tsx`.
const List<({String value, String label})> kGalleryStages =
    <({String value, String label})>[
  (value: '', label: 'Any stage'),
  (value: 'METADATA_READY,PUBLISHED', label: 'Ready to publish'),
  (value: 'COLLECTED', label: 'Collected'),
  (value: 'OCR_CLEAR', label: 'OCR clear'),
  (value: 'OCR_REJECTED', label: 'OCR rejected'),
  (value: 'UPSCALED', label: 'Upscaled'),
  (value: 'REFINED', label: 'Refined'),
  (value: 'COMPATIBLE', label: 'Compatible'),
  (value: 'INCOMPATIBLE', label: 'Incompatible'),
  (value: 'METADATA_READY', label: 'Metadata ready'),
  (value: 'PUBLISHED', label: 'Published'),
  (value: 'QUARANTINED', label: 'Quarantined'),
];

/// Usage chips — same web source (`all|unused|used`).
const List<({String value, String label})> kGalleryUsage =
    <({String value, String label})>[
  (value: 'all', label: 'Any usage'),
  (value: 'unused', label: 'Unused'),
  (value: 'used', label: 'Used'),
];

/// Search + stage + usage lenses (05 §2.5): one horizontal chip strip over
/// a debounced (300 ms) search field. Every change emits a fresh
/// [GalleryQuery] through [onChanged]; chips are icon-paired so state never
/// rides on color alone (04 §4 rule 1).
class GalleryFilterBar extends StatefulWidget {
  const GalleryFilterBar({
    super.key,
    required this.query,
    required this.onChanged,
  });

  final GalleryQuery query;
  final ValueChanged<GalleryQuery> onChanged;

  @override
  State<GalleryFilterBar> createState() => _GalleryFilterBarState();
}

class _GalleryFilterBarState extends State<GalleryFilterBar> {
  late final TextEditingController _search;
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    _search = TextEditingController(text: widget.query.search ?? '');
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _onSearchChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () {
      if (!mounted) {
        return;
      }
      final String trimmed = value.trim();
      if (trimmed == widget.query.search) {
        return;
      }
      widget.onChanged(widget.query.copyWith(search: trimmed));
    });
  }

  @override
  Widget build(BuildContext context) {
    final GalleryQuery query = widget.query;

    return Padding(
      padding: const EdgeInsets.only(left: AppSpacing.lg),
      child: Row(
        children: <Widget>[
          SizedBox(
            width: 150,
            child: TextField(
              controller: _search,
              onChanged: _onSearchChanged,
              style: const TextStyle(fontSize: 13),
              decoration: const InputDecoration(
                hintText: 'Search…',
                isDense: true,
                prefixIcon: Icon(LucideIcons.search, size: 16),
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: SizedBox(
              height: 48,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.only(right: AppSpacing.lg),
                children: <Widget>[
                  for (final ({String value, String label}) stage
                      in kGalleryStages)
                    Padding(
                      padding: const EdgeInsets.only(right: AppSpacing.xs),
                      child: StatusChip(
                        label: stage.label,
                        icon: query.stage == stage.value
                            ? LucideIcons.check
                            : LucideIcons.funnel,
                        tone: query.stage == stage.value
                            ? StatusTone.accent
                            : StatusTone.neutral,
                        onTap: () => widget.onChanged(
                          query.copyWith(stage: stage.value),
                        ),
                      ),
                    ),
                  for (final ({String value, String label}) usage
                      in kGalleryUsage)
                    Padding(
                      padding: const EdgeInsets.only(right: AppSpacing.xs),
                      child: StatusChip(
                        label: usage.label,
                        icon: query.used == usage.value
                            ? LucideIcons.check
                            : _usageIcon(usage.value),
                        tone: query.used == usage.value
                            ? StatusTone.accent
                            : StatusTone.neutral,
                        onTap: () => widget.onChanged(
                          query.copyWith(used: usage.value),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  IconData _usageIcon(String value) => switch (value) {
        'used' => LucideIcons.squareCheck,
        'unused' => LucideIcons.square,
        _ => LucideIcons.images,
      };
}

/// Folder strip (05 §2.5): top level shows the group cards; once a folder
/// scopes the gallery the strip collapses to an "All images" back chip plus
/// the folder's name (web: `inFolder` branch). Loading/empty strips render
/// nothing — the grid carries those states.
class GroupStrip extends StatelessWidget {
  const GroupStrip({
    super.key,
    required this.groups,
    required this.query,
    required this.onSelect,
    required this.onClear,
  });

  final List<GalleryGroup> groups;
  final GalleryQuery query;
  final ValueChanged<String> onSelect;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final String? scopedId = query.groupId;
    if (scopedId != null) {
      final String name = groups
              .where((GalleryGroup group) => group.id == scopedId)
              .map((GalleryGroup group) => group.name)
              .firstOrNull ??
          'Folder';
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
        child: Row(
          children: <Widget>[
            StatusChip(
              label: 'All images',
              icon: LucideIcons.arrowLeft,
              tone: StatusTone.neutral,
              onTap: onClear,
            ),
            const SizedBox(width: AppSpacing.sm),
            const Icon(LucideIcons.folderOpen, size: 16),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: Text(
                name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.labelSmall,
              ),
            ),
          ],
        ),
      );
    }
    if (groups.isEmpty) {
      return const SizedBox.shrink();
    }
    return SizedBox(
      height: 72,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
        itemCount: groups.length,
        separatorBuilder: (_, _) => const SizedBox(width: AppSpacing.sm),
        itemBuilder: (BuildContext context, int index) {
          final GalleryGroup group = groups[index];
          return GroupCard(
            group: group,
            onTap: () => onSelect(group.id),
          );
        },
      ),
    );
  }
}

/// One folder chip-card: name, image count, folder icon, chevron (web
/// `GroupCard` parity).
class GroupCard extends StatelessWidget {
  const GroupCard({super.key, required this.group, this.onTap});

  final GalleryGroup group;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final TextTheme text = Theme.of(context).textTheme;

    return SizedBox(
      width: 176,
      child: AppCard(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.xs,
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(AppRadii.md),
          onTap: onTap,
          child: Row(
            children: <Widget>[
              const Icon(LucideIcons.folder, size: 16),
              const SizedBox(width: AppSpacing.xs),
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    LabelCaps(text: group.name),
                    Text(
                      '${group.count ?? 0} images',
                      style: text.labelSmall?.copyWith(
                        color: AppColors.ink400,
                        fontSize: 10,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.xs),
              const Icon(LucideIcons.chevronRight, size: 16),
            ],
          ),
        ),
      ),
    );
  }
}
