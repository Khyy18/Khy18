class PaymentOrder {
  final String payerName;
  final String payerInn;
  final String payerKpp;
  final String recipientName;
  final String recipientInn;
  final String recipientKpp;
  final String bik;
  final String account;
  final String kbk;
  final String oktmo;
  final double amount;
  final String purpose;

  PaymentOrder({
    required this.payerName,
    required this.payerInn,
    required this.payerKpp,
    required this.recipientName,
    required this.recipientInn,
    required this.recipientKpp,
    required this.bik,
    required this.account,
    required this.kbk,
    required this.oktmo,
    required this.amount,
    required this.purpose,
  });

  factory PaymentOrder.fromJson(Map<String, dynamic> json) {
    return PaymentOrder(
      payerName: json['payer_name'] as String? ?? '',
      payerInn: json['payer_inn'] as String? ?? '',
      payerKpp: json['payer_kpp'] as String? ?? '',
      recipientName: json['recipient_name'] as String? ?? '',
      recipientInn: json['recipient_inn'] as String? ?? '',
      recipientKpp: json['recipient_kpp'] as String? ?? '',
      bik: json['bik'] as String? ?? '',
      account: json['account'] as String? ?? '',
      kbk: json['kbk'] as String? ?? '',
      oktmo: json['oktmo'] as String? ?? '',
      amount: (json['amount'] as num?)?.toDouble() ?? 0,
      purpose: json['purpose'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'payer_name': payerName,
      'payer_inn': payerInn,
      'payer_kpp': payerKpp,
      'recipient_name': recipientName,
      'recipient_inn': recipientInn,
      'recipient_kpp': recipientKpp,
      'bik': bik,
      'account': account,
      'kbk': kbk,
      'oktmo': oktmo,
      'amount': amount,
      'purpose': purpose,
    };
  }
}
