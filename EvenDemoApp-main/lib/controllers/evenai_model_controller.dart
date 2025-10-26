import 'package:demo_ai_even/models/evenai_model.dart';
import 'package:get/get.dart';

/// Stores Q&A items for EvenAI and manages selection.
/// Safe, bounds-checked, and compatible with existing call sites.
class EvenaiModelController extends GetxController {
  /// Reactive list of items shown in the UI.
  final RxList<EvenaiModel> items = <EvenaiModel>[].obs;

  /// Currently selected index (or null).
  final RxnInt selectedIndex = RxnInt();

  /// Add a new item at the top (index 0). Keeps existing behavior.
  void addItem(String title, String content) {
    final newItem = EvenaiModel(
      title: title,
      content: content,
      createdTime: DateTime.now(),
    );
    items.insert(0, newItem);
    // Optional UX: auto-select the newly added item.
    selectedIndex.value = 0;
  }

  /// Remove item by index with full bounds checks.
  void removeItem(int index) {
    if (!_inRange(index)) return;

    items.removeAt(index);

    // Maintain selection coherently.
    final sel = selectedIndex.value;
    if (sel == null) return;

    if (sel == index) {
      // Removed the selected row -> no selection.
      selectedIndex.value = null;
    } else if (sel > index) {
      // Shift selection up by one because list shrank before it.
      selectedIndex.value = sel - 1;
    }
  }

  /// Clear all items and selection.
  void clearItems() {
    items.clear();
    selectedIndex.value = null;
  }

  /// Select item if index is valid.
  void selectItem(int index) {
    if (_inRange(index)) {
      selectedIndex.value = index;
    }
  }

  /// Deselect any selection.
  void deselectItem() {
    selectedIndex.value = null;
  }

  // ---------- Convenience helpers (non-breaking) ----------

  /// Returns the currently selected item or null.
  EvenaiModel? get selectedItem {
    final sel = selectedIndex.value;
    if (sel == null || !_inRange(sel)) return null;
    return items[sel];
  }

  /// Update an existing item (title/content) in place.
  /// Safe even if only one field is provided.
  void updateItem(int index, {String? title, String? content}) {
    if (!_inRange(index)) return;
    final cur = items[index];
    items[index] = EvenaiModel(
      title: title ?? cur.title,
      content: content ?? cur.content,
      createdTime: cur.createdTime,
    );
  }

  /// Replace all items at once (emits a single list update).
  void replaceAll(List<EvenaiModel> newItems) {
    items.assignAll(newItems);
    // Keep selection coherent.
    final sel = selectedIndex.value;
    if (sel != null && !_inRange(sel)) {
      selectedIndex.value = newItems.isEmpty ? null : 0;
    }
  }

  /// Current count.
  int get length => items.length;

  bool _inRange(int i) => i >= 0 && i < items.length;
}
