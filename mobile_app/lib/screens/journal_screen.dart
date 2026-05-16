import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/journal_provider.dart';
import '../theme/app_colors.dart';
import '../widgets/empty_state.dart';

class JournalScreen extends ConsumerStatefulWidget {
  const JournalScreen({super.key});

  @override
  ConsumerState<JournalScreen> createState() => _JournalScreenState();
}

class _JournalScreenState extends ConsumerState<JournalScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(journalProvider.notifier).fetch());
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(journalProvider);

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) context.go('/');
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Журнал операций'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new, size: 20),
            onPressed: () => context.go('/'),
          ),
        ),
      body: Column(
        children: [
          Container(
            margin: const EdgeInsets.all(24),
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: AppColors.primary.withOpacity(0.06),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: AppColors.primary.withOpacity(0.15)),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _BalanceColumn(
                  label: 'Доход',
                  value: state.totalIncome,
                  color: AppColors.success,
                ),
                Container(width: 1, height: 40, color: AppColors.borderLight),
                _BalanceColumn(
                  label: 'Расход',
                  value: state.totalExpense,
                  color: AppColors.expense,
                ),
                Container(width: 1, height: 40, color: AppColors.borderLight),
                _BalanceColumn(
                  label: 'Баланс',
                  value: state.balance,
                  color: AppColors.primary,
                ),
              ],
            ),
          ).animate().fadeIn(duration: 300.ms),
          Expanded(
            child: state.entries.isEmpty
                ? const EmptyState(
                    icon: Icons.book_outlined,
                    message: 'Журнал пуст',
                  )
                : ListView.separated(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    itemCount: state.entries.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 8),
                    itemBuilder: (context, index) {
                      final entry = state.entries[index];
                      final isIncome = entry.type == 'income';
                      return Card(
                        child: ListTile(
                          contentPadding: const EdgeInsets.symmetric(
                              horizontal: 20, vertical: 4),
                          leading: Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              color: (isIncome
                                      ? AppColors.success
                                      : AppColors.expense)
                                  .withOpacity(0.1),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Icon(
                              isIncome
                                  ? Icons.arrow_upward
                                  : Icons.arrow_downward,
                              color: isIncome
                                  ? AppColors.success
                                  : AppColors.expense,
                              size: 20,
                            ),
                          ),
                          title: Text(entry.description),
                          subtitle: Text(entry.date),
                          trailing: Text(
                            '${isIncome ? '+' : '-'}${entry.amount.toStringAsFixed(0)} р.',
                            style: TextStyle(
                              fontWeight: FontWeight.w700,
                              color: isIncome
                                  ? AppColors.success
                                  : AppColors.expense,
                            ),
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    ),
    );
  }
}

class _BalanceColumn extends StatelessWidget {
  final String label;
  final double value;
  final Color color;

  const _BalanceColumn({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          label,
          style: Theme.of(context).textTheme.labelMedium,
        ),
        const SizedBox(height: 4),
        Text(
          '${value.toStringAsFixed(0)} р.',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            color: color,
          ),
        ),
      ],
    );
  }
}
