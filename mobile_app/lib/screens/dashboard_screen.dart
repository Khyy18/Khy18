import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme/app_colors.dart';
import '../widgets/stat_card.dart';

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Добрый день',
                style: GoogleFonts.spaceGrotesk(
                  fontSize: 32,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -1,
                ),
              ).animate().fadeIn(duration: 400.ms),
              const SizedBox(height: 4),
              Text(
                _getDateString(),
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: AppColors.neutral,
                    ),
              ),
              const SizedBox(height: 28),
              Row(
                children: [
                  Expanded(
                    child: StatCard(
                      icon: Icons.people_outline,
                      value: '0',
                      label: 'Сотрудники',
                      animationDelay: 100,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: StatCard(
                      icon: Icons.child_care_outlined,
                      value: '0',
                      label: 'Дети',
                      iconColor: AppColors.success,
                      animationDelay: 200,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: StatCard(
                      icon: Icons.notifications_outlined,
                      value: '0',
                      label: 'Дедлайны',
                      iconColor: AppColors.warning,
                      animationDelay: 300,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 32),
              Text(
                'Функции',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 16),
              GridView.count(
                crossAxisCount: 3,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                childAspectRatio: 0.9,
                children: [
                  _FunctionCard(
                    icon: Icons.calculate_outlined,
                    label: 'Зарплата',
                    onTap: () => context.go('/salary'),
                    delay: 100,
                  ),
                  _FunctionCard(
                    icon: Icons.beach_access_outlined,
                    label: 'Отпуск',
                    onTap: () => context.go('/vacation'),
                    delay: 150,
                  ),
                  _FunctionCard(
                    icon: Icons.local_hospital_outlined,
                    label: 'Больничный',
                    onTap: () => context.go('/sick'),
                    delay: 200,
                  ),
                  _FunctionCard(
                    icon: Icons.calendar_month_outlined,
                    label: 'Табель',
                    onTap: () => context.go('/timesheet'),
                    delay: 250,
                  ),
                  _FunctionCard(
                    icon: Icons.child_care_outlined,
                    label: 'Дети',
                    onTap: () => context.go('/children'),
                    delay: 300,
                  ),
                  _FunctionCard(
                    icon: Icons.book_outlined,
                    label: 'Журнал',
                    onTap: () => context.go('/journal'),
                    delay: 350,
                  ),
                  _FunctionCard(
                    icon: Icons.search,
                    label: 'КБК',
                    onTap: () => context.go('/kbk'),
                    delay: 400,
                  ),
                  _FunctionCard(
                    icon: Icons.notifications_outlined,
                    label: 'Дедлайны',
                    onTap: () => context.go('/reminders'),
                    delay: 450,
                  ),
                  _FunctionCard(
                    icon: Icons.payment_outlined,
                    label: 'Платёжки',
                    onTap: () => context.go('/payment'),
                    delay: 500,
                  ),
                ],
              ),
              const SizedBox(height: 20),
              _AiCard(onTap: () => context.go('/ai_chat')),
            ],
          ),
        ),
      ),
    );
  }

  String _getDateString() {
    final now = DateTime.now();
    const months = [
      '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
      'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
    ];
    return '${now.day} ${months[now.month]} ${now.year}';
  }
}

class _FunctionCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final int delay;

  const _FunctionCard({
    required this.icon,
    required this.label,
    required this.onTap,
    this.delay = 0,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 32, color: AppColors.primary),
              const SizedBox(height: 10),
              Text(
                label,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.labelLarge?.copyWith(
                      fontSize: 12,
                    ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    )
        .animate()
        .fadeIn(delay: Duration(milliseconds: delay), duration: 300.ms)
        .scale(begin: const Offset(0.9, 0.9), end: const Offset(1, 1));
  }
}

class _AiCard extends StatelessWidget {
  final VoidCallback onTap;

  const _AiCard({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppColors.primary, AppColors.primaryLight],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Row(
              children: [
                Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: const Icon(
                    Icons.auto_awesome,
                    color: Colors.white,
                    size: 24,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'AI Ассистент',
                        style: GoogleFonts.spaceGrotesk(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Задайте вопрос по бухгалтерии',
                        style: GoogleFonts.manrope(
                          fontSize: 13,
                          color: Colors.white.withOpacity(0.8),
                        ),
                      ),
                    ],
                  ),
                ),
                const Icon(
                  Icons.arrow_forward_ios,
                  color: Colors.white70,
                  size: 16,
                ),
              ],
            ),
          ),
        ),
      ),
    )
        .animate()
        .fadeIn(delay: 600.ms, duration: 400.ms)
        .slideY(begin: 0.1, end: 0);
  }
}
