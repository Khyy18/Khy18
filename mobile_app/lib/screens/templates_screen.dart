import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme/app_colors.dart';

class TemplatesScreen extends StatelessWidget {
  const TemplatesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) context.go('/more');
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Шаблоны приказов'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new, size: 20),
            onPressed: () => context.go('/more'),
          ),
        ),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Документы',
                  style: GoogleFonts.spaceGrotesk(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.5,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Шаблоны кадровых приказов',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: AppColors.neutral,
                      ),
                ),
                const SizedBox(height: 24),
                const _TemplateCard(
                  icon: Icons.flight_takeoff_outlined,
                  title: 'Приказ на отпуск',
                  subtitle: 'Ежегодный оплачиваемый отпуск',
                  templateType: _TemplateType.vacation,
                  delay: 0,
                ),
                const SizedBox(height: 12),
                const _TemplateCard(
                  icon: Icons.person_add_outlined,
                  title: 'Приказ о приёме',
                  subtitle: 'Приём на работу нового сотрудника',
                  templateType: _TemplateType.hire,
                  delay: 100,
                ),
                const SizedBox(height: 12),
                const _TemplateCard(
                  icon: Icons.person_remove_outlined,
                  title: 'Приказ об увольнении',
                  subtitle: 'Расторжение трудового договора',
                  templateType: _TemplateType.dismissal,
                  delay: 200,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

enum _TemplateType { vacation, hire, dismissal }

class _TemplateCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final _TemplateType templateType;
  final int delay;

  const _TemplateCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.templateType,
    this.delay = 0,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: Theme.of(context).colorScheme.outline, width: 1),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () {
          HapticFeedback.selectionClick();
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => _TemplateFormScreen(templateType: templateType),
            ),
          );
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: AppColors.primary.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, color: AppColors.primary, size: 22),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: GoogleFonts.spaceGrotesk(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: AppColors.neutral,
                          ),
                    ),
                  ],
                ),
              ),
              const Icon(
                Icons.arrow_forward_ios,
                size: 14,
                color: AppColors.neutral,
              ),
            ],
          ),
        ),
      ),
    )
        .animate()
        .fadeIn(delay: Duration(milliseconds: delay), duration: 300.ms)
        .slideX(begin: 0.05, end: 0);
  }
}

class _TemplateFormScreen extends StatefulWidget {
  final _TemplateType templateType;

  const _TemplateFormScreen({required this.templateType});

  @override
  State<_TemplateFormScreen> createState() => _TemplateFormScreenState();
}

class _TemplateFormScreenState extends State<_TemplateFormScreen> {
  final _fioController = TextEditingController();
  final _positionController = TextEditingController();
  final _startDateController = TextEditingController();
  final _endDateController = TextEditingController();
  final _orderNumberController = TextEditingController();

  String? _previewText;

  String get _title {
    switch (widget.templateType) {
      case _TemplateType.vacation:
        return 'Приказ на отпуск';
      case _TemplateType.hire:
        return 'Приказ о приёме';
      case _TemplateType.dismissal:
        return 'Приказ об увольнении';
    }
  }

  void _generatePreview() {
    final fio = _fioController.text.trim();
    final position = _positionController.text.trim();
    final startDate = _startDateController.text.trim();
    final endDate = _endDateController.text.trim();
    final orderNumber = _orderNumberController.text.trim();

    if (fio.isEmpty || position.isEmpty || startDate.isEmpty || orderNumber.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Заполните все обязательные поля'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }

    String text;
    switch (widget.templateType) {
      case _TemplateType.vacation:
        text = '''ПРИКАЗ N $orderNumber

О предоставлении отпуска работнику

Предоставить ежегодный основной оплачиваемый отпуск:

ФИО: $fio
Должность: $position
Период отпуска: с $startDate по $endDate

Основание: заявление работника.

Руководитель _______________
Дата: _______________''';
        break;
      case _TemplateType.hire:
        text = '''ПРИКАЗ N $orderNumber

О приёме на работу

Принять на работу:

ФИО: $fio
Должность: $position
Дата начала работы: $startDate
${endDate.isNotEmpty ? 'Дата окончания договора: $endDate' : 'Договор: бессрочный'}

Условия: согласно трудовому договору.

Руководитель _______________
Дата: _______________''';
        break;
      case _TemplateType.dismissal:
        text = '''ПРИКАЗ N $orderNumber

О прекращении трудового договора

Уволить:

ФИО: $fio
Должность: $position
Дата увольнения: $startDate
${endDate.isNotEmpty ? 'Основание: $endDate' : 'Основание: по собственному желанию (п.3 ч.1 ст.77 ТК РФ)'}

Руководитель _______________
Дата: _______________''';
        break;
    }

    setState(() => _previewText = text);
  }

  @override
  void dispose() {
    _fioController.dispose();
    _positionController.dispose();
    _startDateController.dispose();
    _endDateController.dispose();
    _orderNumberController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_title),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, size: 20),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildField('ФИО сотрудника *', _fioController, 'Иванов Иван Иванович'),
            const SizedBox(height: 16),
            _buildField('Должность *', _positionController, 'Воспитатель'),
            const SizedBox(height: 16),
            _buildField(
              widget.templateType == _TemplateType.dismissal
                  ? 'Дата увольнения *'
                  : 'Дата начала *',
              _startDateController,
              '01.06.2025',
            ),
            const SizedBox(height: 16),
            _buildField(
              widget.templateType == _TemplateType.dismissal
                  ? 'Основание (необязательно)'
                  : 'Дата окончания',
              _endDateController,
              widget.templateType == _TemplateType.dismissal
                  ? 'По собственному желанию'
                  : '28.06.2025',
            ),
            const SizedBox(height: 16),
            _buildField('Номер приказа *', _orderNumberController, '42-к'),
            const SizedBox(height: 32),
            SizedBox(
              width: double.infinity,
              height: 52,
              child: ElevatedButton(
                onPressed: _generatePreview,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                  elevation: 0,
                ),
                child: Text(
                  'Сформировать',
                  style: GoogleFonts.spaceGrotesk(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
            if (_previewText != null) ...[
              const SizedBox(height: 24),
              Card(
                elevation: 0,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                  side: BorderSide(color: Theme.of(context).colorScheme.outline, width: 1),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            width: 36,
                            height: 36,
                            decoration: BoxDecoration(
                              color: AppColors.primary.withOpacity(0.1),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: const Icon(
                              Icons.description_outlined,
                              color: AppColors.primary,
                              size: 18,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Text(
                            'Предварительный просмотр',
                            style: GoogleFonts.spaceGrotesk(
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: Theme.of(context).scaffoldBackgroundColor,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: Theme.of(context).colorScheme.outline),
                        ),
                        child: Text(
                          _previewText!,
                          style: GoogleFonts.manrope(
                            fontSize: 13,
                            height: 1.6,
                            color: Theme.of(context).colorScheme.onSurface,
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                      SizedBox(
                        width: double.infinity,
                        child: OutlinedButton.icon(
                          onPressed: () {
                            Clipboard.setData(
                              ClipboardData(text: _previewText!),
                            );
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('Скопировано в буфер обмена'),
                                behavior: SnackBarBehavior.floating,
                              ),
                            );
                          },
                          icon: const Icon(Icons.copy_outlined, size: 18),
                          label: const Text('Скопировать'),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: AppColors.primary,
                            side: const BorderSide(color: AppColors.primary),
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 8),
                      SizedBox(
                        width: double.infinity,
                        child: OutlinedButton.icon(
                          onPressed: () {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('Функция скачивания в разработке'),
                                behavior: SnackBarBehavior.floating,
                              ),
                            );
                          },
                          icon: const Icon(Icons.download_outlined, size: 18),
                          label: const Text('Скачать'),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: AppColors.neutral,
                            side: BorderSide(color: Theme.of(context).colorScheme.outline),
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ).animate().fadeIn(duration: 400.ms).slideY(begin: 0.05, end: 0),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildField(String label, TextEditingController controller, String hint) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: GoogleFonts.manrope(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
          ),
        ),
        const SizedBox(height: 8),
        TextField(
          controller: controller,
          decoration: InputDecoration(
            hintText: hint,
            filled: true,
            fillColor: Theme.of(context).colorScheme.surface,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide(color: Theme.of(context).colorScheme.outline),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide(color: Theme.of(context).colorScheme.outline),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
            ),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          ),
        ),
      ],
    );
  }
}
