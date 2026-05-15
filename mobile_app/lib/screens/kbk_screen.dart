import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/kbk_code.dart';
import '../providers/employees_provider.dart';
import '../theme/app_colors.dart';

class KbkScreen extends ConsumerStatefulWidget {
  const KbkScreen({super.key});

  @override
  ConsumerState<KbkScreen> createState() => _KbkScreenState();
}

class _KbkScreenState extends ConsumerState<KbkScreen> {
  final _searchController = TextEditingController();
  List<KbkCode> _results = [];
  bool _isLoading = false;

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _search(String query) async {
    if (query.isEmpty) {
      setState(() => _results = []);
      return;
    }
    setState(() => _isLoading = true);
    try {
      final api = ref.read(apiServiceProvider);
      final results = await api.searchKbk(query);
      setState(() => _results = results);
    } catch (_) {
      // Silently handle
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Справочник КБК')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(24),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: 'Поиск по КБК или описанию...',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searchController.text.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _searchController.clear();
                          setState(() => _results = []);
                        },
                      )
                    : null,
              ),
              onChanged: _search,
            ),
          ),
          if (_isLoading)
            const LinearProgressIndicator(color: AppColors.primary),
          Expanded(
            child: _results.isEmpty
                ? Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.search, size: 48,
                            color: AppColors.neutral.withOpacity(0.4)),
                        const SizedBox(height: 16),
                        Text(
                          'Введите запрос для поиска',
                          style: TextStyle(color: AppColors.neutral),
                        ),
                      ],
                    ),
                  )
                : ListView.separated(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    itemCount: _results.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 8),
                    itemBuilder: (context, index) {
                      final kbk = _results[index];
                      return Card(
                        child: ExpansionTile(
                          tilePadding:
                              const EdgeInsets.symmetric(horizontal: 20),
                          title: Text(
                            kbk.code,
                            style: const TextStyle(
                              fontFamily: 'monospace',
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          subtitle: Text(kbk.description, maxLines: 1,
                              overflow: TextOverflow.ellipsis),
                          children: [
                            Padding(
                              padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      const Text('КВР: ',
                                          style: TextStyle(
                                              fontWeight: FontWeight.w600)),
                                      Text(kbk.kvr),
                                    ],
                                  ),
                                  const SizedBox(height: 8),
                                  Text(kbk.description),
                                ],
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
