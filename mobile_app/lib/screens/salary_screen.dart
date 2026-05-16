import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/salary_provider.dart';
import '../theme/app_colors.dart';
import '../widgets/gradient_button.dart';
import '../widgets/result_card.dart';

class SalaryScreen extends ConsumerStatefulWidget {
  const SalaryScreen({super.key});

  @override
  ConsumerState<SalaryScreen> createState() => _SalaryScreenState();
}

class _SalaryScreenState extends ConsumerState<SalaryScreen> {
  final _formKey = GlobalKey<FormState>();
  final _okladController = TextEditingController(text: '30000');
  double _rate = 1.0;
  double _stazhPercent = 10;
  double _categoryPercent = 0;

  @override
  void dispose() {
    _okladController.dispose();
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
          title: const Text('Расчёт зарплаты'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new, size: 20),
            onPressed: () => context.go('/'),
          ),
        ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Параметры',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 20),
              TextFormField(
                controller: _okladController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Оклад, руб.',
                  prefixIcon: Icon(Icons.monetization_on_outlined),
                ),
                validator: (v) =>
                    v == null || v.isEmpty ? 'Введите оклад' : null,
              ),
              const SizedBox(height: 20),
              Text(
                'Ставка',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              SegmentedButton<double>(
                segments: const [
                  ButtonSegment(value: 0.25, label: Text('0.25')),
                  ButtonSegment(value: 0.5, label: Text('0.5')),
                  ButtonSegment(value: 0.75, label: Text('0.75')),
                  ButtonSegment(value: 1.0, label: Text('1.0')),
                ],
                selected: {_rate},
                onSelectionChanged: (v) => setState(() => _rate = v.first),
                style: ButtonStyle(
                  shape: WidgetStatePropertyAll(
                    RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12)),
                  ),
                ),
              ),
              const SizedBox(height: 24),
              _buildSlider(
                'Надбавка за стаж',
                _stazhPercent,
                0,
                30,
                (v) => setState(() => _stazhPercent = v),
              ),
              const SizedBox(height: 16),
              _buildSlider(
                'Надбавка за категорию',
                _categoryPercent,
                0,
                30,
                (v) => setState(() => _categoryPercent = v),
              ),
              const SizedBox(height: 32),
              GradientButton(
                text: 'Рассчитать',
                icon: Icons.calculate,
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
              if (calcState.salaryResult != null) ...[
                const SizedBox(height: 24),
                ResultCard(
                  title: 'Результат расчёта',
                  showGradientHeader: true,
                  rows: [
                    ResultRow(
                        label: 'Оклад',
                        value:
                            '${_fmt(calcState.salaryResult!.oklad)} руб.'),
                    ResultRow(
                        label: 'Ставка',
                        value: '${calcState.salaryResult!.rate}'),
                    ResultRow(
                        label: 'База',
                        value: '${_fmt(calcState.salaryResult!.base)} руб.'),
                    ResultRow(
                        label: 'Стаж',
                        value:
                            '${_fmt(calcState.salaryResult!.stazhAmount)} руб.'),
                    ResultRow(
                        label: 'Категория',
                        value:
                            '${_fmt(calcState.salaryResult!.categoryAmount)} руб.'),
                    ResultRow(
                        label: 'Начислено',
                        value:
                            '${_fmt(calcState.salaryResult!.gross)} руб.'),
                    ResultRow(
                        label: 'НДФЛ 13%',
                        value:
                            '${_fmt(calcState.salaryResult!.ndfl)} руб.',
                        valueColor: AppColors.expense),
                  ],
                  highlightedRow: ResultRow(
                    label: 'На руки',
                    value:
                        '${_fmt(calcState.salaryResult!.netSalary)} руб.',
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    ),
    );
  }

  Widget _buildSlider(
    String label,
    double value,
    double min,
    double max,
    ValueChanged<double> onChanged,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: Theme.of(context).textTheme.titleMedium),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              decoration: BoxDecoration(
                color: AppColors.primary.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                '${value.toInt()}%',
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  color: AppColors.primary,
                ),
              ),
            ),
          ],
        ),
        Slider(
          value: value,
          min: min,
          max: max,
          divisions: (max - min).toInt(),
          onChanged: onChanged,
          activeColor: AppColors.primary,
        ),
      ],
    );
  }

  void _calculate() {
    if (!_formKey.currentState!.validate()) return;
    ref.read(calculationProvider.notifier).calculateSalary(
          oklad: double.parse(_okladController.text),
          rate: _rate,
          stazhPercent: _stazhPercent,
          categoryPercent: _categoryPercent,
        );
  }

  String _fmt(double v) => v.toStringAsFixed(2);
}
