import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../widgets/empty_state.dart';

class TimesheetScreen extends ConsumerWidget {
  const TimesheetScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('Табель')),
      body: const EmptyState(
        icon: Icons.calendar_month_outlined,
        message: 'Добавьте сотрудников для ведения табеля учёта рабочего времени',
      ),
    );
  }
}
