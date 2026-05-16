import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../services/api_service.dart';
import '../widgets/empty_state.dart';

class TimesheetScreen extends ConsumerStatefulWidget {
  const TimesheetScreen({super.key});

  @override
  ConsumerState<TimesheetScreen> createState() => _TimesheetScreenState();
}

class _TimesheetScreenState extends ConsumerState<TimesheetScreen> {
  void _showBulkMarkDialog() {
    showDialog(
      context: context,
      builder: (ctx) => const _BulkMarkDialog(),
    );
  }

  @override
  Widget build(BuildContext context) {
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
          message:
              'Добавьте сотрудников для ведения табеля учёта рабочего времени',
        ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: _showBulkMarkDialog,
          icon: const Icon(Icons.check_circle_outline),
          label: const Text('Отметить всех'),
        ),
      ),
    );
  }
}

class _BulkMarkDialog extends StatefulWidget {
  const _BulkMarkDialog();

  @override
  State<_BulkMarkDialog> createState() => _BulkMarkDialogState();
}

class _BulkMarkDialogState extends State<_BulkMarkDialog> {
  DateTime _selectedDate = DateTime.now();
  String _selectedStatus = 'present';
  bool _loading = false;

  static const _statusOptions = <String, String>{
    'present': 'Явка',
    'absent': 'Неявка',
    'sick': 'Больничный',
    'vacation': 'Отпуск',
  };

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _selectedDate,
      firstDate: DateTime(2020),
      lastDate: DateTime(2030),
    );
    if (picked != null) {
      setState(() => _selectedDate = picked);
    }
  }

  Future<void> _submit() async {
    setState(() => _loading = true);
    try {
      final api = ApiService();
      // Fetch employees to get IDs
      final employees = await api.getEmployees();
      if (employees.isEmpty) {
        if (mounted) {
          Navigator.of(context).pop();
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Нет сотрудников для отметки')),
          );
        }
        return;
      }
      final ids = employees.map((e) => e.id).whereType<int>().toList();
      final dateStr = DateFormat('yyyy-MM-dd').format(_selectedDate);
      final result = await api.bulkMarkTimesheet(
        date: dateStr,
        status: _selectedStatus,
        employeeIds: ids,
      );
      if (mounted) {
        Navigator.of(context).pop();
        final updated = result['updated'] ?? 0;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Отмечено сотрудников: $updated')),
        );
      }
    } catch (e) {
      if (mounted) {
        Navigator.of(context).pop();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Ошибка: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final dateStr = DateFormat('dd.MM.yyyy').format(_selectedDate);
    return AlertDialog(
      title: const Text('Отметить всех'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Дата'),
            subtitle: Text(dateStr),
            trailing: const Icon(Icons.calendar_today),
            onTap: _pickDate,
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            value: _selectedStatus,
            decoration: const InputDecoration(
              labelText: 'Статус',
              border: OutlineInputBorder(),
            ),
            items: _statusOptions.entries
                .map((e) => DropdownMenuItem(
                      value: e.key,
                      child: Text(e.value),
                    ))
                .toList(),
            onChanged: (v) {
              if (v != null) setState(() => _selectedStatus = v);
            },
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: _loading ? null : () => Navigator.of(context).pop(),
          child: const Text('Отмена'),
        ),
        FilledButton(
          onPressed: _loading ? null : _submit,
          child: _loading
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Отметить'),
        ),
      ],
    );
  }
}
