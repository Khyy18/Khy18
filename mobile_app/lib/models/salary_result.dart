class SalaryResult {
  final double oklad;
  final double rate;
  final double stazhPercent;
  final double categoryPercent;
  final double base;
  final double stazhAmount;
  final double categoryAmount;
  final double gross;
  final double ndfl;
  final double pfr;
  final double oms;
  final double fss;
  final double fssNs;
  final double netSalary;
  final double totalCharges;

  SalaryResult({
    required this.oklad,
    required this.rate,
    required this.stazhPercent,
    required this.categoryPercent,
    required this.base,
    required this.stazhAmount,
    required this.categoryAmount,
    required this.gross,
    required this.ndfl,
    required this.pfr,
    required this.oms,
    required this.fss,
    required this.fssNs,
    required this.netSalary,
    required this.totalCharges,
  });

  factory SalaryResult.fromJson(Map<String, dynamic> json) {
    return SalaryResult(
      oklad: (json['oklad'] as num?)?.toDouble() ?? 0,
      rate: (json['rate'] as num?)?.toDouble() ?? 1.0,
      stazhPercent: (json['stazh_percent'] as num?)?.toDouble() ?? 0,
      categoryPercent: (json['category_percent'] as num?)?.toDouble() ?? 0,
      base: (json['base'] as num?)?.toDouble() ?? 0,
      stazhAmount: (json['stazh_amount'] as num?)?.toDouble() ?? 0,
      categoryAmount: (json['category_amount'] as num?)?.toDouble() ?? 0,
      gross: (json['gross'] as num?)?.toDouble() ?? 0,
      ndfl: (json['ndfl'] as num?)?.toDouble() ?? 0,
      pfr: (json['pfr'] as num?)?.toDouble() ?? 0,
      oms: (json['oms'] as num?)?.toDouble() ?? 0,
      fss: (json['fss'] as num?)?.toDouble() ?? 0,
      fssNs: (json['fss_ns'] as num?)?.toDouble() ?? 0,
      netSalary: (json['net_salary'] as num?)?.toDouble() ?? 0,
      totalCharges: (json['total_charges'] as num?)?.toDouble() ?? 0,
    );
  }
}
