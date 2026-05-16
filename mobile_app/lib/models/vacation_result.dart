class VacationResult {
  final double totalEarnings;
  final int days;
  final double avgDaily;
  final double vacationPay;
  final double ndfl;
  final double netPay;

  VacationResult({
    required this.totalEarnings,
    required this.days,
    required this.avgDaily,
    required this.vacationPay,
    required this.ndfl,
    required this.netPay,
  });

  factory VacationResult.fromJson(Map<String, dynamic> json) {
    return VacationResult(
      totalEarnings: (json['total_earnings'] as num?)?.toDouble() ?? 0,
      days: (json['days'] as num?)?.toInt() ?? 0,
      avgDaily: (json['avg_daily'] as num?)?.toDouble() ?? 0,
      vacationPay: (json['vacation_pay'] as num?)?.toDouble() ?? 0,
      ndfl: (json['ndfl'] as num?)?.toDouble() ?? 0,
      netPay: (json['net_pay'] as num?)?.toDouble() ?? 0,
    );
  }
}
