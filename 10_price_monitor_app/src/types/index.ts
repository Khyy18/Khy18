export interface PricePoint {
  date: string;
  price: number;
}

export interface Product {
  id: string;
  title: string;
  image: string;
  currentPrice: number;
  oldPrice: number;
  discount: number;
  category: string;
  marketplace: 'WB' | 'Ozon';
  priceHistory: PricePoint[];
  rating: number;
  reviewsSummary: string;
  affiliateUrl: string;
}

export interface Category {
  id: string;
  name: string;
  icon: string;
  productCount: number;
}

export interface Alert {
  id: string;
  keyword: string;
  maxPrice: number;
  category: string;
  active: boolean;
  createdAt: string;
}

export interface UserProfile {
  id: string;
  name: string;
  email: string;
  subscription: 'free' | 'vip';
  referralCode: string;
  totalSaved: number;
  dealsTracked: number;
  bestDeal: number;
}
