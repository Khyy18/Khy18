class KbkCode {
  final String code;
  final String kvr;
  final String description;

  KbkCode({
    required this.code,
    required this.kvr,
    required this.description,
  });

  factory KbkCode.fromJson(Map<String, dynamic> json) {
    return KbkCode(
      code: json['code'] as String? ?? '',
      kvr: json['kvr'] as String? ?? '',
      description: json['description'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'code': code,
      'kvr': kvr,
      'description': description,
    };
  }
}
