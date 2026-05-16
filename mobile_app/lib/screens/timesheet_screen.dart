import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../widgets/empty_state.dart';

class TimesheetScreen extends ConsumerWidget {
  const TimesheetScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) context.go('/');
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Табель'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new, size: 20),
            onPressed: () => context.go('/'),
          ),
        ),
        body: const EmptyState(
          icon: Icons.calendar_month_outlined,
          message: 'Добавьте сотрудников для ведения табеля учёта рабочего времени',
        ),
      ),
    );
  }
}
