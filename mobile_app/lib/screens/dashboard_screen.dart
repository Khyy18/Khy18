import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/notification_service.dart';
import '../theme/app_colors.dart';
import '../widgets/floating_nav_bar.dart';
import '../widgets/stat_card.dart';

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      body: Stack(
        children: [
          // Background gradient
          Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Color(0xFFFFFFFF),
                  Color(0xFFF5F3FF),
                ],
              ),
            ),
          ),
          // Main content
          SafeArea(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(24, 20, 24, 100),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Header with particle dots behind
                  Stack(
                    children: [
                      SizedBox(
                        width: double.infinity,
                        height: 60,
                        child: CustomPaint(
                          painter: _ParticleDotsPainter(),
                        ),
                      ),
                      Column(
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
                            style: Theme.of(context)
                                .textTheme
                                .bodyMedium
                                ?.copyWith(
                                  color: AppColors.neutral,
                                ),
                          ),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 28),
                  const _NotificationBanner(),
                  const SizedBox(height: 16),
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
          // Floating nav bar at bottom
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: FloatingNavBar(
              currentIndex: 0,
              onTap: (index) {
                switch (index) {
                  case 0:
                    break; // Already on dashboard
                  case 1:
                    context.go('/salary');
                    break;
                  case 2:
                    context.go('/children');
                    break;
                  case 3:
                    context.go('/reminders');
                    break;
                }
              },
            ),
          ),
        ],
      ),
    );
  }

  String _getDateString() {
    final now = DateTime.now();
    const months = [
      '',
      'января',
      'февраля',
      'марта',
      'апреля',
      'мая',
      'июня',
      'июля',
      'августа',
      'сентября',
      'октября',
      'ноября',
      'декабря',
    ];
    return '${now.day} ${months[now.month]} ${now.year}';
  }
}

/// Decorative particle dots painted behind the header
class _ParticleDotsPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF6366F1).withOpacity(0.06)
      ..style = PaintingStyle.fill;

    // Fixed pseudo-random positions for decorative dots
    final dots = <Offset>[
      Offset(size.width * 0.85, size.height * 0.2),
      Offset(size.width * 0.72, size.height * 0.7),
      Offset(size.width * 0.92, size.height * 0.5),
      Offset(size.width * 0.60, size.height * 0.15),
      Offset(size.width * 0.78, size.height * 0.85),
      Offset(size.width * 0.95, size.height * 0.3),
      Offset(size.width * 0.65, size.height * 0.55),
      Offset(size.width * 0.88, size.height * 0.75),
      Offset(size.width * 0.55, size.height * 0.35),
      Offset(size.width * 0.70, size.height * 0.45),
      Offset(size.width * 0.82, size.height * 0.10),
      Offset(size.width * 0.58, size.height * 0.80),
      Offset(size.width * 0.90, size.height * 0.65),
    ];

    final sizes = <double>[
      3.0, 4.5, 2.5, 5.0, 3.5, 2.0, 4.0, 3.0, 5.5, 2.5, 4.0, 3.5, 2.0
    ];

    for (var i = 0; i < dots.length; i++) {
      canvas.drawCircle(dots[i], sizes[i], paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
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
        onTap: () {
          HapticFeedback.selectionClick();
          onTap();
        },
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
    return ClipRRect(
      borderRadius: BorderRadius.circular(20),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: Container(
          decoration: BoxDecoration(
            color: const Color(0xFF6366F1).withOpacity(0.12),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: Colors.white.withOpacity(0.2),
              width: 1,
            ),
            gradient: LinearGradient(
              colors: [
                AppColors.primary.withOpacity(0.3),
                AppColors.primaryLight.withOpacity(0.1),
              ],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
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
        ),
      ),
    )
        .animate()
        .fadeIn(delay: 600.ms, duration: 400.ms)
        .slideY(begin: 0.1, end: 0);
  }
}

class _NotificationBanner extends StatefulWidget {
  const _NotificationBanner();

  @override
  State<_NotificationBanner> createState() => _NotificationBannerState();
}

class _NotificationBannerState extends State<_NotificationBanner> {
  bool _dismissed = false;

  @override
  Widget build(BuildContext context) {
    if (_dismissed) return const SizedBox.shrink();

    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            Icon(
              Icons.notifications_none_rounded,
              color: AppColors.primary,
              size: 24,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                'Включить уведомления',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.w500,
                    ),
              ),
            ),
            TextButton(
              onPressed: () async {
                try {
                  await NotificationService.requestPermission();
                } catch (_) {}
                setState(() => _dismissed = true);
              },
              child: const Text('Включить'),
            ),
            IconButton(
              icon: const Icon(Icons.close, size: 18),
              onPressed: () => setState(() => _dismissed = true),
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
            ),
          ],
        ),
      ),
    ).animate().fadeIn(duration: 300.ms).slideY(begin: -0.2, end: 0);
  }
}
