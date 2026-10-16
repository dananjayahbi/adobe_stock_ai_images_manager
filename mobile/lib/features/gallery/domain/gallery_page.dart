import 'image_record.dart';

/// One page of gallery results (the `RecordListResponse` envelope's
/// payload: `items` + `total`; `page`/`page_size` are echoed back by the
/// server but the grid never needs them).
class GalleryPage {
  const GalleryPage({required this.items, required this.total});

  final List<ImageRecord> items;

  /// Server-side total for the current lens — drives the load-more cap.
  final int total;

  bool get isEmpty => items.isEmpty;
}
