import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../theme/app_colors.dart';

class ResultCard extends StatelessWidget {
  final String? title;
  final List<ResultRow> rows;
  final ResultRow? highlightedRow;
  final bool showGradientHeader;

  const ResultCard({
    super.key,
    this.title,
    required this.rows,
    this.highlightedRow,
    this.showGradientHeader = false,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (title != null) ...[
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
              decoration: showGradientHeader
                  ? const BoxDecoration(
                      gradient: LinearGradient(
                        colors: [AppColors.primary, AppColors.primaryLight],
                      ),
                      borderRadius: BorderRadius.only(
                        topLeft: Radius.circular(20),
                        topRight: Radius.circular(20),
                      ),
                    )
                  : null,
              child: Text(
                title!,
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      color: showGradientHeader ? Colors.white : null,
                    ),
              ),
            ),
            if (!showGradientHeader) const Divider(),
          ],
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
            child: Column(
              children: [
                for (int i = 0; i < rows.length; i++) ...[
                  _buildRow(context, rows[i]),
                  if (i < rows.length - 1)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Divider(
                          color: Theme.of(context).colorScheme.outline,
                          height: 1),
                    ),
                ],
                if (highlightedRow != null) ...[
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 12),
                    decoration: BoxDecoration(
                      color: AppColors.primary.withOpacity(0.08),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: _buildRow(context, highlightedRow!,
                        isBold: true, color: AppColors.primary),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    ).animate().fadeIn(duration: 300.ms).slideY(begin: 0.05, end: 0);
  }

  Widget _buildRow(BuildContext context, ResultRow row,
      {bool isBold = false, Color? color}) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Flexible(
          child: Text(
            row.label,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  fontWeight: isBold ? FontWeight.w700 : null,
                  color: color,
                ),
          ),
        ),
        const SizedBox(width: 16),
        Text(
          row.value,
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                fontWeight: isBold ? FontWeight.w700 : FontWeight.w600,
                color: color ?? row.valueColor,
                fontFamily: 'monospace',
              ),
        ),
      ],
    );
  }
}

class ResultRow {
  final String label;
  final String value;
  final Color? valueColor;

  const ResultRow({
    required this.label,
    required this.value,
    this.valueColor,
  });
}
