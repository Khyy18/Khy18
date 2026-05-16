class Employee {
  final int? id;
  final String name;
  final String position;
  final double oklad;
  final double rate;
  final double stazhPercent;
  final double categoryPercent;
  final int? chatId;

  Employee({
    this.id,
    required this.name,
    required this.position,
    required this.oklad,
    required this.rate,
    required this.stazhPercent,
    required this.categoryPercent,
    this.chatId,
  });

  factory Employee.fromJson(Map<String, dynamic> json) {
    return Employee(
      id: json['id'] as int?,
      name: json['name'] as String? ?? '',
      position: json['position'] as String? ?? '',
      oklad: (json['oklad'] as num?)?.toDouble() ?? 0,
      rate: (json['rate'] as num?)?.toDouble() ?? 1.0,
      stazhPercent: (json['stazh_percent'] as num?)?.toDouble() ?? 0,
      categoryPercent: (json['category_percent'] as num?)?.toDouble() ?? 0,
      chatId: json['chat_id'] as int?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      if (id != null) 'id': id,
      'name': name,
      'position': position,
      'oklad': oklad,
      'rate': rate,
      'stazh_percent': stazhPercent,
      'category_percent': categoryPercent,
      if (chatId != null) 'chat_id': chatId,
    };
  }
}
