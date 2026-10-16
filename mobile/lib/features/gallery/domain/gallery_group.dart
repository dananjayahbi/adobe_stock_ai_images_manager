/// A gallery folder (`GroupResponse`: `id`, `name`, `image_count`).
class GalleryGroup {
  const GalleryGroup({required this.id, required this.name, this.count});

  final String id;
  final String name;

  /// Live image count from `image_count`; null when the payload omitted it.
  final int? count;
}
