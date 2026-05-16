import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme/app_colors.dart';

class CalendarScreen extends StatefulWidget {
  const CalendarScreen({super.key});

  @override
  State<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends State<CalendarScreen> {
  late int _year;
  late int _month;

  // Production calendar holidays for 2024-2025 Russia
  static final Map<String, List<int>> _holidays = {
    '2024-01': [1, 2, 3, 4, 5, 6, 7, 8],
    '2024-02': [23],
    '2024-03': [8],
    '2024-05': [1, 9],
    '2024-06': [12],
    '2024-11': [4],
    '2024-12': [31],
    '2025-01': [1, 2, 3, 4, 5, 6, 7, 8],
    '2025-02': [23, 24],
    '2025-03': [8],
    '2025-05': [1, 2, 9],
    '2025-06': [12, 13],
    '2025-11': [3, 4],
    '2025-12': [31],
  };

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _year = now.year;
    _month = now.month;
  }

  void _prevMonth() {
    HapticFeedback.selectionClick();
    setState(() {
      _month--;
      if (_month < 1) {
        _month = 12;
        _year--;
      }
    });
  }

  void _nextMonth() {
    HapticFeedback.selectionClick();
    setState(() {
      _month++;
      if (_month > 12) {
        _month = 1;
        _year++;
      }
    });
  }

  bool _isHoliday(int day) {
    final key = '$_year-${_month.toString().padLeft(2, '0')}';
    return _holidays[key]?.contains(day) ?? false;
  }

  bool _isWeekend(int day) {
    final date = DateTime(_year, _month, day);
    return date.weekday == DateTime.saturday || date.weekday == DateTime.sunday;
  }

  Map<String, int> _getMonthStats() {
    final daysInMonth = DateTime(_year, _month + 1, 0).day;
    int workDays = 0;
    int weekends = 0;
    int holidays = 0;

    for (int d = 1; d <= daysInMonth; d++) {
      if (_isHoliday(d)) {
        holidays++;
      } else if (_isWeekend(d)) {
        weekends++;
      } else {
        workDays++;
      }
    }

    return {'work': workDays, 'weekend': weekends, 'holiday': holidays};
  }

  String _monthName(int month) {
    const names = [
      'Январь', 'Февраль', 'Март', 'Апрель',
      'Май', 'Июнь', 'Июль', 'Август',
      'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
    ];
    return names[month - 1];
  }

  @override
  Widget build(BuildContext context) {
    final stats = _getMonthStats();
    final daysInMonth = DateTime(_year, _month + 1, 0).day;
    final firstWeekday = DateTime(_year, _month, 1).weekday;

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) context.go('/more');
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Производственный календарь'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new, size: 20),
            onPressed: () => context.go('/more'),
          ),
        ),
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            children: [
              // Month navigation
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  IconButton(
                    onPressed: _prevMonth,
                    icon: const Icon(Icons.chevron_left_rounded, size: 28),
                    color: AppColors.primary,
                  ),
                  Text(
                    '${_monthName(_month)} $_year',
                    style: GoogleFonts.spaceGrotesk(
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  IconButton(
                    onPressed: _nextMonth,
                    icon: const Icon(Icons.chevron_right_rounded, size: 28),
                    color: AppColors.primary,
                  ),
                ],
              ).animate().fadeIn(duration: 300.ms),
              const SizedBox(height: 20),
              // Stats cards
              Row(
                children: [
                  _StatChip(
                    label: 'Рабочих',
                    value: '${stats['work']}',
                    color: AppColors.primary,
                  ),
                  const SizedBox(width: 8),
                  _StatChip(
                    label: 'Выходных',
                    value: '${stats['weekend']}',
                    color: AppColors.neutral,
                  ),
                  const SizedBox(width: 8),
                  _StatChip(
                    label: 'Праздников',
                    value: '${stats['holiday']}',
                    color: AppColors.expense,
                  ),
                ],
              ).animate().fadeIn(delay: 100.ms, duration: 300.ms),
              const SizedBox(height: 24),
              // Weekday headers
              Row(
                children: ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
                    .map((day) => Expanded(
                          child: Center(
                            child: Text(
                              day,
                              style: GoogleFonts.manrope(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: day == 'Сб' || day == 'Вс'
                                    ? AppColors.expense.withOpacity(0.7)
                                    : AppColors.neutral,
                              ),
                            ),
                          ),
                        ))
                    .toList(),
              ),
              const SizedBox(height: 8),
              // Calendar grid
              _buildCalendarGrid(daysInMonth, firstWeekday),
              const SizedBox(height: 24),
              // Legend
              _buildLegend(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCalendarGrid(int daysInMonth, int firstWeekday) {
    final cells = <Widget>[];

    // Empty cells before first day
    for (int i = 1; i < firstWeekday; i++) {
      cells.add(const SizedBox());
    }

    // Day cells
    for (int d = 1; d <= daysInMonth; d++) {
      final isHol = _isHoliday(d);
      final isWknd = _isWeekend(d);
      final isToday = d == DateTime.now().day &&
          _month == DateTime.now().month &&
          _year == DateTime.now().year;

      Color bgColor;
      Color textColor;

      if (isToday) {
        bgColor = AppColors.primary;
        textColor = Colors.white;
      } else if (isHol) {
        bgColor = AppColors.expense.withOpacity(0.12);
        textColor = AppColors.expense;
      } else if (isWknd) {
        bgColor = AppColors.neutral.withOpacity(0.08);
        textColor = AppColors.neutral;
      } else {
        bgColor = Colors.transparent;
        textColor = AppColors.textPrimaryLight;
      }

      cells.add(
        Container(
          margin: const EdgeInsets.all(2),
          decoration: BoxDecoration(
            color: bgColor,
            borderRadius: BorderRadius.circular(8),
            border: isToday
                ? null
                : Border.all(
                    color: AppColors.borderLight.withOpacity(0.5),
                    width: 0.5,
                  ),
          ),
          alignment: Alignment.center,
          child: Text(
            '$d',
            style: GoogleFonts.spaceGrotesk(
              fontSize: 13,
              fontWeight: isToday ? FontWeight.w700 : FontWeight.w500,
              color: textColor,
            ),
          ),
        ),
      );
    }

    return GridView.count(
      crossAxisCount: 7,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      childAspectRatio: 1.2,
      children: cells,
    ).animate().fadeIn(delay: 200.ms, duration: 300.ms);
  }

  Widget _buildLegend() {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: AppColors.borderLight, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            _legendItem(AppColors.primary, 'Сегодня'),
            _legendItem(AppColors.expense.withOpacity(0.4), 'Праздник'),
            _legendItem(AppColors.neutral.withOpacity(0.3), 'Выходной'),
          ],
        ),
      ),
    ).animate().fadeIn(delay: 300.ms, duration: 300.ms);
  }

  Widget _legendItem(Color color, String label) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(4),
          ),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: GoogleFonts.manrope(
            fontSize: 12,
            color: AppColors.textSecondaryLight,
          ),
        ),
      ],
    );
  }
}

class _StatChip extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _StatChip({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
        decoration: BoxDecoration(
          color: color.withOpacity(0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withOpacity(0.2)),
        ),
        child: Column(
          children: [
            Text(
              value,
              style: GoogleFonts.spaceGrotesk(
                fontSize: 22,
                fontWeight: FontWeight.w700,
                color: color,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: GoogleFonts.manrope(
                fontSize: 11,
                color: color.withOpacity(0.8),
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
