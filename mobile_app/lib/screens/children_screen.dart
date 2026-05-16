import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/children_provider.dart';
import '../theme/app_colors.dart';
import '../widgets/empty_state.dart';

class ChildrenScreen extends ConsumerStatefulWidget {
  const ChildrenScreen({super.key});

  @override
  ConsumerState<ChildrenScreen> createState() => _ChildrenScreenState();
}

class _ChildrenScreenState extends ConsumerState<ChildrenScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(childrenProvider.notifier).fetch());
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(childrenProvider);

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) context.go('/');
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Дети'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new, size: 20),
            onPressed: () => context.go('/'),
          ),
        ),
      body: state.children.isEmpty
          ? const EmptyState(
              icon: Icons.child_care_outlined,
              message: 'Список детей пуст.\nДобавьте первого ребёнка.',
            )
          : ListView.separated(
              padding: const EdgeInsets.all(24),
              itemCount: state.children.length,
              separatorBuilder: (_, __) => const SizedBox(height: 12),
              itemBuilder: (context, index) {
                final child = state.children[index];
                return Dismissible(
                  key: ValueKey(child.id),
                  direction: DismissDirection.endToStart,
                  onDismissed: (_) {
                    if (child.id != null) {
                      ref.read(childrenProvider.notifier).delete(child.id!);
                    }
                  },
                  background: Container(
                    alignment: Alignment.centerRight,
                    padding: const EdgeInsets.only(right: 24),
                    decoration: BoxDecoration(
                      color: AppColors.expense.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const Icon(Icons.delete_outline,
                        color: AppColors.expense),
                  ),
                  child: Card(
                    child: ListTile(
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 20, vertical: 8),
                      leading: CircleAvatar(
                        backgroundColor: AppColors.primary.withOpacity(0.1),
                        child: Text(
                          child.name.isNotEmpty
                              ? child.name[0].toUpperCase()
                              : '?',
                          style: const TextStyle(
                            color: AppColors.primary,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                      title: Text(child.name),
                      subtitle: Text(child.group),
                      trailing: Text(
                        '${child.monthlyFee.toInt()} руб.',
                        style: const TextStyle(
                          fontWeight: FontWeight.w600,
                          color: AppColors.primary,
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
        floatingActionButton: FloatingActionButton(
        onPressed: () {},
        backgroundColor: AppColors.primary,
        child: const Icon(Icons.add, color: Colors.white),
      ),
      ),
    );
  }
}
