import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../theme/app_colors.dart';
import '../widgets/floating_nav_bar.dart';

class MoreScreen extends StatelessWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) context.go('/');
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Ещё'),
          automaticallyImplyLeading: false,
        ),
        body: Stack(
          children: [
            SafeArea(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 24, 24, 100),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Дополнительно',
                      style: GoogleFonts.spaceGrotesk(
                        fontSize: 22,
                        fontWeight: FontWeight.w700,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 24),
                    _HubCard(
                      icon: Icons.person_outline,
                      title: 'Профиль',
                      subtitle: 'Настройки аккаунта',
                      onTap: () => context.go('/profile'),
                      delay: 0,
                    ),
                    const SizedBox(height: 12),
                    _HubCard(
                      icon: Icons.notifications_outlined,
                      title: 'Напоминания',
                      subtitle: 'Дедлайны и уведомления',
                      onTap: () => context.go('/reminders'),
                      delay: 100,
                    ),
                    const SizedBox(height: 12),
                    _HubCard(
                      icon: Icons.search,
                      title: 'КБК',
                      subtitle: 'Справочник кодов бюджетной классификации',
                      onTap: () => context.go('/kbk'),
                      delay: 200,
                    ),
                    const SizedBox(height: 12),
                    _HubCard(
                      icon: Icons.description_outlined,
                      title: 'Шаблоны приказов',
                      subtitle: 'Приказы на отпуск, приём, увольнение',
                      onTap: () => context.go('/templates'),
                      delay: 300,
                    ),
                    const SizedBox(height: 12),
                    _HubCard(
                      icon: Icons.calendar_month_outlined,
                      title: 'Производственный календарь',
                      subtitle: 'Рабочие и выходные дни 2024-2025',
                      onTap: () => context.go('/calendar'),
                      delay: 400,
                    ),
                    const SizedBox(height: 12),
                    _HubCard(
                      icon: Icons.auto_awesome,
                      title: 'AI Ассистент',
                      subtitle: 'Задайте вопрос по бухгалтерии',
                      onTap: () => context.go('/ai_chat'),
                      delay: 500,
                    ),
                  ],
                ),
              ),
            ),
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: FloatingNavBar(
                currentIndex: 3,
                onTap: (index) {
                  switch (index) {
                    case 0:
                      context.go('/');
                      break;
                    case 1:
                      context.go('/calculations');
                      break;
                    case 2:
                      context.go('/data');
                      break;
                    case 3:
                      break;
                  }
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HubCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final int delay;

  const _HubCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
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
          onTap();
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
                            color: Theme.of(context).colorScheme.onSurfaceVariant,
                          ),
                    ),
                  ],
                ),
              ),
              Icon(
                Icons.arrow_forward_ios,
                size: 14,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
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
