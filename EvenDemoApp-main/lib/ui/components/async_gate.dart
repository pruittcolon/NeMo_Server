import 'package:flutter/material.dart';

typedef AsyncBuilder<T> = Widget Function(BuildContext context, T data);

class AsyncGate<T> extends StatelessWidget {
  const AsyncGate({
    super.key,
    required this.future,
    required this.builder,
    this.loading,
    this.error,
    this.initialData,
  });

  final Future<T> future;
  final AsyncBuilder<T> builder;
  final Widget? loading;
  final Widget? error;
  final T? initialData;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<T>(
      future: future,
      initialData: initialData,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return loading ?? _defaultLoading(context);
        }

        if (snapshot.hasError) {
          return error ?? _defaultError(context, snapshot.error);
        }

        if (!snapshot.hasData) {
          return error ?? _defaultError(context, 'No data');
        }

        return builder(context, snapshot.data as T);
      },
    );
  }

  Widget _defaultLoading(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: const [
          SizedBox(
            width: 34,
            height: 34,
            child: CircularProgressIndicator(strokeWidth: 3),
          ),
          SizedBox(height: 12),
          Text('Loading...'),
        ],
      ),
    );
  }

  Widget _defaultError(BuildContext context, Object? error) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.error_outline, color: Theme.of(context).colorScheme.error),
          const SizedBox(height: 8),
          Text('Error: $error'),
        ],
      ),
    );
  }
}
