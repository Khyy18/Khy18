import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../widgets/gradient_button.dart';

class PaymentScreen extends ConsumerStatefulWidget {
  const PaymentScreen({super.key});

  @override
  ConsumerState<PaymentScreen> createState() => _PaymentScreenState();
}

class _PaymentScreenState extends ConsumerState<PaymentScreen> {
  int _currentStep = 0;

  final _payerNameController = TextEditingController();
  final _payerInnController = TextEditingController();
  final _recipientNameController = TextEditingController();
  final _recipientInnController = TextEditingController();
  final _amountController = TextEditingController();
  final _purposeController = TextEditingController();
  final _kbkController = TextEditingController();

  @override
  void dispose() {
    _payerNameController.dispose();
    _payerInnController.dispose();
    _recipientNameController.dispose();
    _recipientInnController.dispose();
    _amountController.dispose();
    _purposeController.dispose();
    _kbkController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Платёжное поручение')),
      body: Stepper(
        currentStep: _currentStep,
        type: StepperType.vertical,
        onStepContinue: () {
          if (_currentStep < 2) {
            setState(() => _currentStep++);
          }
        },
        onStepCancel: () {
          if (_currentStep > 0) {
            setState(() => _currentStep--);
          }
        },
        controlsBuilder: (context, details) {
          return Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Row(
              children: [
                if (_currentStep < 2)
                  ElevatedButton(
                    onPressed: details.onStepContinue,
                    child: const Text('Далее'),
                  )
                else
                  GradientButton(
                    text: 'Сформировать',
                    icon: Icons.payment,
                    onPressed: () {},
                  ),
                const SizedBox(width: 12),
                if (_currentStep > 0)
                  TextButton(
                    onPressed: details.onStepCancel,
                    child: const Text('Назад'),
                  ),
              ],
            ),
          );
        },
        steps: [
          Step(
            title: const Text('Плательщик'),
            isActive: _currentStep >= 0,
            state: _currentStep > 0 ? StepState.complete : StepState.indexed,
            content: Column(
              children: [
                const SizedBox(height: 8),
                TextFormField(
                  controller: _payerNameController,
                  decoration:
                      const InputDecoration(labelText: 'Наименование'),
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _payerInnController,
                  decoration: const InputDecoration(labelText: 'ИНН'),
                  keyboardType: TextInputType.number,
                ),
              ],
            ),
          ),
          Step(
            title: const Text('Получатель'),
            isActive: _currentStep >= 1,
            state: _currentStep > 1 ? StepState.complete : StepState.indexed,
            content: Column(
              children: [
                const SizedBox(height: 8),
                TextFormField(
                  controller: _recipientNameController,
                  decoration:
                      const InputDecoration(labelText: 'Наименование'),
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _recipientInnController,
                  decoration: const InputDecoration(labelText: 'ИНН'),
                  keyboardType: TextInputType.number,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _kbkController,
                  decoration: const InputDecoration(labelText: 'КБК'),
                ),
              ],
            ),
          ),
          Step(
            title: const Text('Сумма и назначение'),
            isActive: _currentStep >= 2,
            content: Column(
              children: [
                const SizedBox(height: 8),
                TextFormField(
                  controller: _amountController,
                  decoration: const InputDecoration(
                    labelText: 'Сумма, руб.',
                    prefixIcon: Icon(Icons.monetization_on_outlined),
                  ),
                  keyboardType: TextInputType.number,
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _purposeController,
                  decoration:
                      const InputDecoration(labelText: 'Назначение платежа'),
                  maxLines: 3,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
