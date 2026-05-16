import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
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

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) context.go('/');
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Напоминания'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new, size: 20),
            onPressed: () => context.go('/'),
          ),
        ),
        body: _buildBody(state),
      ),
    );
  }

  Widget _buildBody(RemindersState state) {
    if (state.isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (state.error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, size: 48, color: AppColors.expense),
            const SizedBox(height: 16),
            const Text('Не удалось загрузить данные'),
            const SizedBox(height: 12),
            ElevatedButton(
              onPressed: () => ref.read(remindersProvider.notifier).fetch(),
              child: const Text('Повторить'),
            ),
          ],
        ),
      );
    }

    if (state.reminders.isEmpty) {
      return const EmptyState(
        icon: Icons.notifications_outlined,
        message: 'Нет активных напоминаний',
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.all(24),
      itemCount: state.reminders.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (context, index) {
        final reminder = state.reminders[index];
        return Card(
          child: ListTile(
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
            leading: Container(
              width: 12,
              height: 12,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: reminder.enabled
                    ? AppColors.success
                    : Theme.of(context).colorScheme.onSurfaceVariant,
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
    );
  }
}
