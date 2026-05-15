import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/salary_provider.dart';
import '../theme/app_colors.dart';
import '../widgets/gradient_button.dart';
import '../widgets/result_card.dart';

class SickScreen extends ConsumerStatefulWidget {
  const SickScreen({super.key});

  @override
  ConsumerState<SickScreen> createState() => _SickScreenState();
}

class _SickScreenState extends ConsumerState<SickScreen> {
  final _earningsController = TextEditingController(text: '720000');
  int _days = 10;
  String _stazhBracket = '5-8';

  final _brackets = const ['<5', '5-8', '>8'];
  final _bracketLabels = const ['До 5 лет (60%)', '5-8 лет (80%)', 'Более 8 (100%)'];

  @override
  void dispose() {
    _earningsController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final calcState = ref.watch(calculationProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Больничный')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Расчёт больничного',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 24),
            TextFormField(
              controller: _earningsController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Доход за 2 года, руб.',
                prefixIcon: Icon(Icons.account_balance_wallet_outlined),
              ),
            ),
            const SizedBox(height: 20),
            Text('Стаж', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              children: List.generate(_brackets.length, (i) {
                final selected = _stazhBracket == _brackets[i];
                return ChoiceChip(
                  label: Text(_bracketLabels[i]),
                  selected: selected,
                  onSelected: (_) =>
                      setState(() => _stazhBracket = _brackets[i]),
                  selectedColor: AppColors.primary.withOpacity(0.15),
                  labelStyle: TextStyle(
                    color: selected ? AppColors.primary : null,
                    fontWeight: selected ? FontWeight.w600 : null,
                  ),
                );
              }),
            ),
            const SizedBox(height: 24),
            Row(
              children: [
                Text('Дней', style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: AppColors.borderLight),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        icon: const Icon(Icons.remove, size: 18),
                        onPressed:
                            _days > 1 ? () => setState(() => _days--) : null,
                      ),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        child: Text('$_days',
                            style: Theme.of(context).textTheme.headlineSmall),
                      ),
                      IconButton(
                        icon: const Icon(Icons.add, size: 18),
                        onPressed: () => setState(() => _days++),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 32),
            GradientButton(
              text: 'Рассчитать',
              icon: Icons.local_hospital,
              isLoading: calcState.isLoading,
              onPressed: _calculate,
            ),
            if (calcState.error != null) ...[
              const SizedBox(height: 16),
              Text(calcState.error!,
                  style: const TextStyle(color: AppColors.expense)),
            ],
            if (calcState.sickResult != null) ...[
              const SizedBox(height: 24),
              ResultCard(
                title: 'Больничный лист',
                showGradientHeader: true,
                rows: [
                  ResultRow(
                      label: 'Доход за 2 года',
                      value:
                          '${calcState.sickResult!.earnings2y.toStringAsFixed(2)} руб.'),
                  ResultRow(
                      label: 'Среднедневной',
                      value:
                          '${calcState.sickResult!.avgDaily.toStringAsFixed(2)} руб.'),
                  ResultRow(
                      label: 'Процент',
                      value: '${calcState.sickResult!.percent.toInt()}%'),
                  ResultRow(
                      label: 'Дней',
                      value: '${calcState.sickResult!.days}'),
                ],
                highlightedRow: ResultRow(
                  label: 'К выплате',
                  value:
                      '${calcState.sickResult!.sickPay.toStringAsFixed(2)} руб.',
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  void _calculate() {
    final earnings = double.tryParse(_earningsController.text);
    if (earnings == null || earnings <= 0) return;
    ref.read(calculationProvider.notifier).calculateSick(
          earnings2y: earnings,
          stazhBracket: _stazhBracket,
          days: _days,
        );
  }
}
