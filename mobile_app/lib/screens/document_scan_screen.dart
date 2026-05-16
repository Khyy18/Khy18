import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';
import '../services/file_export_service.dart';
import '../theme/app_colors.dart';
import '../widgets/gradient_button.dart';
import '../widgets/result_card.dart';

class DocumentScanScreen extends ConsumerStatefulWidget {
  const DocumentScanScreen({super.key});

  @override
  ConsumerState<DocumentScanScreen> createState() =>
      _DocumentScanScreenState();
}

class _DocumentScanScreenState extends ConsumerState<DocumentScanScreen> {
  final ImagePicker _picker = ImagePicker();
  final ApiService _api = ApiService();

  File? _imageFile;
  bool _isProcessing = false;
  bool _isExporting = false;
  String? _error;
  String _docType = '';
  Map<String, TextEditingController> _fieldControllers = {};

  @override
  void dispose() {
    for (final c in _fieldControllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _pickImage(ImageSource source) async {
    try {
      final picked = await _picker.pickImage(
        source: source,
        maxWidth: 1920,
        maxHeight: 1920,
        imageQuality: 85,
      );
      if (picked != null) {
        setState(() {
          _imageFile = File(picked.path);
          _error = null;
          _docType = '';
          for (final c in _fieldControllers.values) {
            c.dispose();
          }
          _fieldControllers = {};
        });
      }
    } catch (e) {
      setState(() => _error = 'Не удалось выбрать изображение');
    }
  }

  Future<void> _processOcr() async {
    if (_imageFile == null) return;
    setState(() {
      _isProcessing = true;
      _error = null;
    });
    try {
      final bytes = await _imageFile!.readAsBytes();
      final base64Image = base64Encode(bytes);
      final result = await _api.processOcr(base64Image);

      final fields = (result['fields'] as Map<String, dynamic>?) ?? {};
      _docType = (result['doc_type'] as String?) ?? 'document';

      for (final c in _fieldControllers.values) {
        c.dispose();
      }
      _fieldControllers = {};
      for (final entry in fields.entries) {
        _fieldControllers[entry.key] =
            TextEditingController(text: entry.value.toString());
      }

      setState(() => _isProcessing = false);
    } catch (e) {
      setState(() {
        _isProcessing = false;
        _error = 'Ошибка распознавания: $e';
      });
    }
  }

  Future<void> _exportToExcel() async {
    if (_fieldControllers.isEmpty) return;
    setState(() {
      _isExporting = true;
      _error = null;
    });
    try {
      final fields = <String, String>{};
      for (final entry in _fieldControllers.entries) {
        fields[entry.key] = entry.value.text;
      }
      final bytes = await _api.exportOcrToExcel(fields, _docType);
      await saveAndOpenFile(bytes, 'ocr_$_docType.xlsx');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Excel сохранен'),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } catch (e) {
      setState(() => _error = 'Ошибка экспорта: $e');
    } finally {
      setState(() => _isExporting = false);
    }
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
          title: const Text('Скан документа'),
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
                'Распознавание документа',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 24),
              Row(
                children: [
                  Expanded(
                    child: _SourceButton(
                      icon: Icons.camera_alt_outlined,
                      label: 'Камера',
                      onTap: () => _pickImage(ImageSource.camera),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _SourceButton(
                      icon: Icons.photo_library_outlined,
                      label: 'Галерея',
                      onTap: () => _pickImage(ImageSource.gallery),
                    ),
                  ),
                ],
              ),
              if (_imageFile != null) ...[
                const SizedBox(height: 24),
                ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: Image.file(
                    _imageFile!,
                    height: 200,
                    width: double.infinity,
                    fit: BoxFit.cover,
                  ),
                ),
                const SizedBox(height: 24),
                GradientButton(
                  text: 'Распознать',
                  icon: Icons.document_scanner,
                  isLoading: _isProcessing,
                  onPressed: _processOcr,
                ),
              ],
              if (_error != null) ...[
                const SizedBox(height: 16),
                Text(
                  _error!,
                  style: const TextStyle(color: AppColors.expense),
                ),
              ],
              if (_fieldControllers.isNotEmpty) ...[
                const SizedBox(height: 24),
                ResultCard(
                  title: 'Результат: $_docType',
                  showGradientHeader: true,
                  rows: _fieldControllers.entries
                      .map((e) => ResultRow(
                            label: e.key,
                            value: e.value.text,
                          ))
                      .toList(),
                ),
                const SizedBox(height: 16),
                ..._fieldControllers.entries.map((entry) => Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: TextFormField(
                        controller: entry.value,
                        decoration: InputDecoration(
                          labelText: entry.key,
                          prefixIcon:
                              const Icon(Icons.edit_outlined, size: 20),
                        ),
                      ),
                    )),
                const SizedBox(height: 16),
                GradientButton(
                  text: 'Сохранить в Excel',
                  icon: Icons.download,
                  isLoading: _isExporting,
                  onPressed: _exportToExcel,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _SourceButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _SourceButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.primary.withOpacity(0.06),
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 20),
          child: Column(
            children: [
              Icon(icon, size: 32, color: AppColors.primary),
              const SizedBox(height: 8),
              Text(
                label,
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: AppColors.primary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
