import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';

import '../services/sync_service.dart';
import '../theme/app_colors.dart';

class SyncIndicator extends ConsumerStatefulWidget {
  const SyncIndicator({super.key});

  @override
  ConsumerState<SyncIndicator> createState() => _SyncIndicatorState();
}

class _SyncIndicatorState extends ConsumerState<SyncIndicator> {
  int _pendingCount = 0;
  bool _isOnline = true;

  @override
  void initState() {
    super.initState();
    _init();
  }

  void _init() {
    final syncService = ref.read(syncServiceProvider);
    _pendingCount = syncService.pendingCount;
    syncService.pendingCountStream.listen((count) {
      if (mounted) {
        setState(() => _pendingCount = count);
      }
    });
    syncService.isOnline().then((online) {
      if (mounted) {
        setState(() => _isOnline = online);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_pendingCount == 0 && _isOnline) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: AppColors.success.withOpacity(0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: AppColors.success.withOpacity(0.2),
            width: 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.check_circle_outline,
              size: 16,
              color: AppColors.success,
            ),
            const SizedBox(width: 6),
            Text(
              'Синхронизировано',
              style: GoogleFonts.manrope(
                fontSize: 12,
                fontWeight: FontWeight.w500,
                color: AppColors.success,
              ),
            ),
          ],
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.warning.withOpacity(0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: AppColors.warning.withOpacity(0.2),
          width: 1,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.sync,
            size: 16,
            color: AppColors.warning,
          ),
          const SizedBox(width: 6),
          Text(
            'Синхронизация: $_pendingCount ${_pluralOps(_pendingCount)} в очереди',
            style: GoogleFonts.manrope(
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: AppColors.warning,
            ),
          ),
        ],
      ),
    );
  }

  String _pluralOps(int count) {
    if (count % 10 == 1 && count % 100 != 11) return 'операция';
    if (count % 10 >= 2 &&
        count % 10 <= 4 &&
        (count % 100 < 10 || count % 100 >= 20)) return 'операции';
    return 'операций';
  }
}
