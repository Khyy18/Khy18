import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/reminders_provider.dart';
import '../theme/app_colors.dart';
import '../widgets/empty_state.dart';

class RemindersScreen extends ConsumerStatefulWidget {
  const RemindersScreen({super.key});

  @override
  ConsumerState<RemindersScreen> createState() => _RemindersScreenState();
}

class _RemindersScreenState extends ConsumerState<RemindersScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(remindersProvider.notifier).fetch());
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(remindersProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Напоминания')),
      body: state.reminders.isEmpty
          ? const EmptyState(
              icon: Icons.notifications_outlined,
              message: 'Нет активных напоминаний',
            )
          : ListView.separated(
              padding: const EdgeInsets.all(24),
              itemCount: state.reminders.length,
              separatorBuilder: (_, __) => const SizedBox(height: 8),
              itemBuilder: (context, index) {
                final reminder = state.reminders[index];
                return Card(
                  child: ListTile(
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 20, vertical: 8),
                    leading: Container(
                      width: 12,
                      height: 12,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: reminder.enabled
                            ? AppColors.success
                            : AppColors.neutral,
                      ),
                    ),
                    title: Text(reminder.title),
                    subtitle: Text(reminder.deadline),
                    trailing: Switch(
                      value: reminder.enabled,
                      onChanged: (_) {},
                      activeColor: AppColors.primary,
                    ),
                  ),
                );
              },
            ),
    );
  }
}
