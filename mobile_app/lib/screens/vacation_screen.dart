import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/salary_provider.dart';
import '../services/api_service.dart';
import '../theme/app_colors.dart';
import '../widgets/gradient_button.dart';
import '../widgets/result_card.dart';

class VacationScreen extends ConsumerStatefulWidget {
  const VacationScreen({super.key});

  @override
  ConsumerState<VacationScreen> createState() => _VacationScreenState();
}

class _VacationScreenState extends ConsumerState<VacationScreen> {
  final _earningsController = TextEditingController(text: '360000');
  int _days = 28;

  @override
  void dispose() {
    _earningsController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final calcState = ref.watch(calculationProvider);

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) context.go('/');
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Отпускные'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new, size: 20),
            onPressed: () => context.go('/'),
          ),
        ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Расчёт отпускных',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 24),
            TextFormField(
              controller: _earningsController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Доход за 12 месяцев, руб.',
                prefixIcon: Icon(Icons.account_balance_wallet_outlined),
              ),
            ),
            const SizedBox(height: 24),
            Row(
              children: [
                Text(
                  'Дни отпуска',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const Spacer(),
                _DaysCounter(
                  value: _days,
                  onChanged: (v) => setState(() => _days = v),
                ),
              ],
            ),
            const SizedBox(height: 32),
            GradientButton(
              text: 'Рассчитать',
              icon: Icons.beach_access,
              isLoading: calcState.isLoading,
              onPressed: _calculate,
            ),
            if (calcState.error != null) ...[
              const SizedBox(height: 16),
              Text(
                calcState.error!,
                style: const TextStyle(color: AppColors.expense),
              ),
            ],
            if (calcState.vacationResult != null) ...[
              const SizedBox(height: 24),
              ResultCard(
                title: 'Отпускные',
                showGradientHeader: true,
                rows: [
                  ResultRow(
                      label: 'Доход за 12 мес.',
                      value:
                          '${_fmt(calcState.vacationResult!.totalEarnings)} руб.'),
                  ResultRow(
                      label: 'Дней отпуска',
                      value: '${calcState.vacationResult!.days}'),
                  ResultRow(
                      label: 'Среднедневной',
                      value:
                          '${_fmt(calcState.vacationResult!.avgDaily)} руб.'),
                  ResultRow(
                      label: 'Начислено',
                      value:
                          '${_fmt(calcState.vacationResult!.vacationPay)} руб.'),
                  ResultRow(
                      label: 'НДФЛ',
                      value: '${_fmt(calcState.vacationResult!.ndfl)} руб.',
                      valueColor: AppColors.expense),
                ],
                highlightedRow: ResultRow(
                  label: 'К выплате',
                  value: '${_fmt(calcState.vacationResult!.netPay)} руб.',
                ),
              ),
              const SizedBox(height: 16),
              GradientButton(
                text: 'Скачать Excel',
                icon: Icons.download,
                onPressed: _exportExcel,
              ),
            ],
          ],
        ),
      ),
    ),
    );
  }

  void _exportExcel() async {
    try {
      final api = ApiService();
      await api.exportVacationExcel(
        totalEarnings: double.parse(_earningsController.text),
        days: _days,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Excel скачан'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Ошибка: $e'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  void _calculate() {
    final earnings = double.tryParse(_earningsController.text);
    if (earnings == null || earnings <= 0) return;
    ref.read(calculationProvider.notifier).calculateVacation(
          totalEarnings: earnings,
          days: _days,
        );
  }

  String _fmt(double v) => v.toStringAsFixed(2);
}

class _DaysCounter extends StatelessWidget {
  final int value;
  final ValueChanged<int> onChanged;

  const _DaysCounter({required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: Border.all(color: AppColors.borderLight),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            icon: const Icon(Icons.remove, size: 18),
            onPressed: value > 1 ? () => onChanged(value - 1) : null,
            splashRadius: 18,
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Text(
              '$value',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
          ),
          IconButton(
            icon: const Icon(Icons.add, size: 18),
            onPressed: () => onChanged(value + 1),
            splashRadius: 18,
          ),
        ],
      ),
    );
  }
}
