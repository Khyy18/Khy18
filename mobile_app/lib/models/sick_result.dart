class SickResult {
  final double earnings2y;
  final String stazhBracket;
  final int days;
  final double avgDaily;
  final double percent;
  final double sickPay;

  SickResult({
    required this.earnings2y,
    required this.stazhBracket,
    required this.days,
    required this.avgDaily,
    required this.percent,
    required this.sickPay,
  });

  factory SickResult.fromJson(Map<String, dynamic> json) {
    return SickResult(
      earnings2y: (json['earnings_2y'] as num?)?.toDouble() ?? 0,
      stazhBracket: json['stazh_bracket'] as String? ?? '',
      days: (json['days'] as num?)?.toInt() ?? 0,
      avgDaily: (json['avg_daily'] as num?)?.toDouble() ?? 0,
      percent: (json['percent'] as num?)?.toDouble() ?? 0,
      sickPay: (json['sick_pay'] as num?)?.toDouble() ?? 0,
    );
  }
}
