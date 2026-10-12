from dataclasses import dataclass
from datetime import date
from hashlib import sha256

from weather import Weather


TREND_AS_OF = date(2026, 10, 12)
TREND_SOURCES = (
    (
        "Fashionista · Fall 2026 street style",
        "https://fashionista.com/2026/03/street-style-trends-fall-2026",
    ),
    ("British Vogue · Autumn/Winter 2026", "https://www.vogue.co.uk/autumn-winter-2026"),
)


@dataclass(frozen=True)
class Outfit:
    title: str
    style: str
    trend: str
    palette: str
    colors: tuple[tuple[str, str], ...]
    color_style: str
    color_tip: str
    top: str
    bottom: str
    outerwear: str
    shoes: str
    accessory: str
    reason: str


_SEASONAL_TRENDS = {
    "spring": ("ライトレイヤード", "プレッピーMIX", "クリーンカラー"),
    "summer": ("スポーツMIX", "メッシュ/シアー", "バギーシルエット"),
    "autumn": (
        "赤×ブルーの大胆配色",
        "オーバーサイズレイヤード",
        "テック・ユーティリティ",
        "グレー×ワイン",
        "レトロスポーツ",
    ),
    "winter": (
        "グレー×ワイン",
        "質感ミックス",
        "オーバーサイズレイヤード",
        "赤×ブルーの大胆配色",
        "モノトーンレイヤード",
    ),
}

_WARDROBE = {
    "メンズ": (
        {
            "title": "シティ・ユーティリティ",
            "style": "ストリート",
            "trends": (
                "テック・ユーティリティ", "オーバーサイズレイヤード", "グレー×ワイン",
                "ブラウン・アースカラー", "ライトレイヤード",
            ),
            "palette": "チャコール × オリーブ × チェリーレッド",
            "colors": (("チャコール", "#36363D"), ("オリーブ", "#78816A"), ("チェリーレッド", "#B52D45")),
            "color_style": "アースカラー",
            "color_tip": "チャコールをベースに、オリーブで季節感。赤は小物に少量だけ。",
            "hot_top": "ボックスシルエットの無地T",
            "mild_top": "ワンポイントの長袖T",
            "cool_top": "ハーフジップのニット",
            "bottom": "ゆるめのカーゴパンツ",
            "light_outer": "ナイロンシャツ",
            "mid_outer": "ワークジャケット",
            "cold_outer": "中綿ブルゾン",
            "shoes": "ボリュームスニーカー",
            "accessory": "ミニショルダー",
        },
        {
            "title": "ネオ・プレッピー",
            "style": "きれいめ",
            "trends": ("赤×ブルーの大胆配色", "グレー×ワイン", "レトロスポーツ", "プレッピーMIX"),
            "palette": "ネイビー × アイボリー × チェリーレッド",
            "colors": (("ネイビー", "#243956"), ("アイボリー", "#F1EBDD"), ("チェリーレッド", "#B52D45")),
            "color_style": "赤×ブルー",
            "color_tip": "ネイビーを主役にアイボリーで抜け感を作り、赤は小物で一点投入。",
            "hot_top": "開襟シャツ",
            "mild_top": "オックスフォードシャツ",
            "cool_top": "ケーブルニット",
            "bottom": "ストレートチノ",
            "light_outer": "薄手のカーディガン",
            "mid_outer": "テーラードジャケット",
            "cold_outer": "ウールコート",
            "shoes": "ローファー",
            "accessory": "細めのベルト",
        },
        {
            "title": "スポーツ・ミックス",
            "style": "スポーティ",
            "trends": ("赤×ブルーの大胆配色", "オーバーサイズレイヤード", "スポーツMIX", "バギーシルエット"),
            "palette": "コバルトブルー × グレー × レッド",
            "colors": (("コバルトブルー", "#315FAD"), ("グレー", "#A6A7AA"), ("レッド", "#C43145")),
            "color_style": "赤×ブルー",
            "color_tip": "ブルーとグレーを軸に、赤を10%だけ効かせてスポーティに。",
            "hot_top": "ドライタッチのゲームシャツ",
            "mild_top": "ラグランのロングT",
            "cool_top": "スウェットハーフジップ",
            "bottom": "ライン入りトラックパンツ",
            "light_outer": "ライトトラックジャケット",
            "mid_outer": "トラックジャケット",
            "cold_outer": "シェルジャケット",
            "shoes": "レトロランニングスニーカー",
            "accessory": "キャップ",
        },
        {
            "title": "リラックス・デニム",
            "style": "ストリート",
            "trends": (
                "オーバーサイズレイヤード", "赤×ブルーの大胆配色", "バギーシルエット",
                "ライトレイヤード", "クリーンカラー",
            ),
            "palette": "デニムブルー × オフホワイト × レッド",
            "colors": (("デニムブルー", "#80A9CD"), ("オフホワイト", "#F4F0E8"), ("レッド", "#BA3448")),
            "color_style": "赤×ブルー",
            "color_tip": "デニムの青を主役に、白で軽さを出して赤をワンポイントに。",
            "hot_top": "ヘビーウェイトT",
            "mild_top": "ボーダーの長袖T",
            "cool_top": "スウェット",
            "bottom": "バギーデニム",
            "light_outer": "デニムシャツ",
            "mid_outer": "デニムジャケット",
            "cold_outer": "ボア付きデニムジャケット",
            "shoes": "キャンバススニーカー",
            "accessory": "トートバッグ",
        },
        {
            "title": "グレー・レザーMIX",
            "style": "ストリート",
            "trends": ("グレー×ワイン", "質感ミックス", "オーバーサイズレイヤード"),
            "palette": "スレート × チャコール × シルバー",
            "colors": (("スレート", "#64666D"), ("チャコール", "#303137"), ("シルバー", "#C5C6CB")),
            "color_style": "モノトーン",
            "color_tip": "レザーの質感を主役に、グレーの濃淡でまとめて。",
            "hot_top": "ヘビーウェイトT",
            "mild_top": "クルーネックの長袖T",
            "cool_top": "タートルネックニット",
            "bottom": "ワイドスラックス",
            "light_outer": "レザーシャツ",
            "mid_outer": "レザーブルゾン",
            "cold_outer": "シアリング風ブルゾン",
            "shoes": "レザーブーツ",
            "accessory": "シルバーアクセサリー",
        },
        {
            "title": "キャンパス・レトロ",
            "style": "きれいめ",
            "trends": ("レトロスポーツ", "赤×ブルーの大胆配色", "プレッピーMIX", "スポーツMIX"),
            "palette": "ネイビー × クリーム × バーガンディ",
            "colors": (("ネイビー", "#263A58"), ("クリーム", "#F1EBDD"), ("バーガンディ", "#762E49")),
            "color_style": "赤×ブルー",
            "color_tip": "ネイビーにクリームを合わせ、赤みのある小物でレトロ感を。",
            "hot_top": "ボーダーポロシャツ",
            "mild_top": "オックスフォードシャツ",
            "cool_top": "クルーネックニット",
            "bottom": "ストレートデニム",
            "light_outer": "コットンカーディガン",
            "mid_outer": "バーシティジャケット",
            "cold_outer": "ダッフルコート",
            "shoes": "レトロランニングスニーカー",
            "accessory": "キャンバストート",
        },
        {
            "title": "テック・トレイル",
            "style": "スポーティ",
            "trends": ("テック・ユーティリティ", "オーバーサイズレイヤード", "スポーツMIX", "バギーシルエット"),
            "palette": "グラファイト × セージ × ブルー",
            "colors": (("グラファイト", "#34363C"), ("セージ", "#9BA894"), ("ブルー", "#4269A8")),
            "color_style": "アースカラー",
            "color_tip": "落ち着いたベースにブルーを少量足して、機能服を都会的に。",
            "hot_top": "ドライメッシュT",
            "mild_top": "テック素材のシャツ",
            "cool_top": "サーマルロングT",
            "bottom": "ナイロンカーゴパンツ",
            "light_outer": "軽量シェルベスト",
            "mid_outer": "テックシェルジャケット",
            "cold_outer": "中綿シェルパーカ",
            "shoes": "トレイルスニーカー",
            "accessory": "ユーティリティポーチ",
        },
        {
            "title": "スカーフ・クラシック",
            "style": "きれいめ",
            "trends": ("グレー×ワイン", "質感ミックス", "オーバーサイズレイヤード", "プレッピーMIX"),
            "palette": "グレー × ワイン × パール",
            "colors": (("グレー", "#85868B"), ("ワイン", "#713C56"), ("パール", "#E7E0D8")),
            "color_style": "ニュートラル",
            "color_tip": "グレーを主役にワイン色のスカーフを一点。顔まわりに色を集めて。",
            "hot_top": "ニットポロ",
            "mild_top": "バンドカラーシャツ",
            "cool_top": "ラムウールニット",
            "bottom": "センタープレススラックス",
            "light_outer": "シャツジャケット",
            "mid_outer": "ステンカラーコート",
            "cold_outer": "ウールチェスターコート",
            "shoes": "レザーローファー",
            "accessory": "トライアングルスカーフ",
        },
    ),
    "レディース": (
        {
            "title": "シアー・レイヤード",
            "style": "きれいめ",
            "trends": ("グレー×ワイン", "質感ミックス", "メッシュ/シアー", "ライトレイヤード"),
            "palette": "パール × グレー × ワイン",
            "colors": (("パール", "#E7E0D8"), ("グレー", "#96989D"), ("ワイン", "#713C56")),
            "color_style": "ニュートラル",
            "color_tip": "グレーとパールを重ね、ワイン色を差して奥行きをプラス。",
            "hot_top": "シアーシャツ",
            "mild_top": "シアーシャツ＋タンクトップ",
            "cool_top": "リブニット",
            "bottom": "ワイドスラックス",
            "light_outer": "クロップドカーディガン",
            "mid_outer": "ショート丈トレンチ",
            "cold_outer": "ミドル丈ウールコート",
            "shoes": "フラットシューズ",
            "accessory": "小さめのショルダーバッグ",
        },
        {
            "title": "レトロ・プレッピー",
            "style": "きれいめ",
            "trends": ("赤×ブルーの大胆配色", "グレー×ワイン", "レトロスポーツ", "プレッピーMIX"),
            "palette": "ネイビー × キャメル × チェリーレッド",
            "colors": (("ネイビー", "#243956"), ("キャメル", "#B28B63"), ("チェリーレッド", "#B52D45")),
            "color_style": "赤×ブルー",
            "color_tip": "ネイビーとキャメルの定番配色に、赤を靴下やバッグで一点だけ。",
            "hot_top": "ポロニット",
            "mild_top": "ストライプシャツ",
            "cool_top": "ケーブルカーディガン",
            "bottom": "プリーツスカート",
            "light_outer": "薄手のニットベスト",
            "mid_outer": "ブレザー",
            "cold_outer": "ダッフルコート",
            "shoes": "ローファー＋ソックス",
            "accessory": "細フレームのアイウェア",
        },
        {
            "title": "ワントーン・モード",
            "style": "きれいめ",
            "trends": (
                "グレー×ワイン", "質感ミックス", "モノトーンレイヤード",
                "クリーンカラー", "ブラウン・アースカラー",
            ),
            "palette": "グラファイト × グレー × ワイン",
            "colors": (("グラファイト", "#3B3B40"), ("グレー", "#AAA9AC"), ("ワイン", "#713C56")),
            "color_style": "モノトーン",
            "color_tip": "グレーを濃淡でつないで、ワイン色を小さく差すと洗練された印象に。",
            "hot_top": "コンパクトT",
            "mild_top": "落ち感のあるブラウス",
            "cool_top": "ハイゲージニット",
            "bottom": "タック入りワイドパンツ",
            "light_outer": "シャツジャケット",
            "mid_outer": "ロングジレ",
            "cold_outer": "ロングコート",
            "shoes": "ポインテッドトゥのフラットシューズ",
            "accessory": "メタルアクセサリー",
        },
        {
            "title": "アクティブ・シティ",
            "style": "スポーティ",
            "trends": ("テック・ユーティリティ", "赤×ブルーの大胆配色", "スポーツMIX", "バギーシルエット"),
            "palette": "スモークグレー × ブルー × レッド",
            "colors": (("スモークグレー", "#A5A6AA"), ("ブルー", "#4269A8"), ("レッド", "#BA3448")),
            "color_style": "赤×ブルー",
            "color_tip": "グレーとブルーを主役に、赤はキャップやバッグで軽く効かせて。",
            "hot_top": "リブタンク＋シアーシャツ",
            "mild_top": "ハーフジップのスウェット",
            "cool_top": "フリーストップス",
            "bottom": "ナイロンカーゴスカート",
            "light_outer": "軽量ナイロンベスト",
            "mid_outer": "ジップアップブルゾン",
            "cold_outer": "中綿シェルジャケット",
            "shoes": "厚底ランニングスニーカー",
            "accessory": "ナイロンのクロスボディバッグ",
        },
        {
            "title": "ダークロマンティック",
            "style": "きれいめ",
            "trends": ("グレー×ワイン", "質感ミックス", "オーバーサイズレイヤード"),
            "palette": "ブラック × スレート × ワイン",
            "colors": (("ブラック", "#222228"), ("スレート", "#696A72"), ("ワイン", "#713C56")),
            "color_style": "モノトーン",
            "color_tip": "レースや落ち感のある素材を重ね、深い色で引き締めて。",
            "hot_top": "軽やかなレースブラウス",
            "mild_top": "シアーブラウス",
            "cool_top": "ベルベット調のトップス",
            "bottom": "ロングフレアスカート",
            "light_outer": "ショート丈カーディガン",
            "mid_outer": "ベルト付きジャケット",
            "cold_outer": "ロングウールコート",
            "shoes": "ストラップシューズ",
            "accessory": "小ぶりのハンドバッグ",
        },
        {
            "title": "カラーブロック・プレッピー",
            "style": "きれいめ",
            "trends": ("赤×ブルーの大胆配色", "レトロスポーツ", "プレッピーMIX", "スポーツMIX"),
            "palette": "ブルー × オフホワイト × チェリーレッド",
            "colors": (("ブルー", "#4269A8"), ("オフホワイト", "#F3EFE8"), ("チェリーレッド", "#B52D45")),
            "color_style": "赤×ブルー",
            "color_tip": "ブルーを広く使い、赤はバッグやソックスに絞るとまとまりやすい。",
            "hot_top": "ポロシャツ",
            "mild_top": "ストライプのシャツ",
            "cool_top": "Vネックニット",
            "bottom": "プリーツミニスカート",
            "light_outer": "ニットベスト",
            "mid_outer": "ショートブレザー",
            "cold_outer": "ダッフルコート",
            "shoes": "ローファー＋ソックス",
            "accessory": "ミニショルダーバッグ",
        },
        {
            "title": "グレー・テクスチャーミックス",
            "style": "きれいめ",
            "trends": ("グレー×ワイン", "質感ミックス", "モノトーンレイヤード", "メッシュ/シアー"),
            "palette": "グレージュ × チャコール × ワイン",
            "colors": (("グレージュ", "#B8B2AA"), ("チャコール", "#393A40"), ("ワイン", "#713C56")),
            "color_style": "モノトーン",
            "color_tip": "ニットやシアー素材を重ね、ワイン色を小さく効かせて。",
            "hot_top": "シアー素材の半袖トップス",
            "mild_top": "リブニット＋シアーシャツ",
            "cool_top": "ローゲージニット",
            "bottom": "落ち感のあるロングスカート",
            "light_outer": "透け感のあるシャツジャケット",
            "mid_outer": "オーバーサイズカーディガン",
            "cold_outer": "ボリュームスリーブコート",
            "shoes": "スクエアトゥブーツ",
            "accessory": "質感のあるミニバッグ",
        },
        {
            "title": "スカーフ・シティ",
            "style": "ストリート",
            "trends": ("グレー×ワイン", "オーバーサイズレイヤード", "ライトレイヤード", "クリーンカラー"),
            "palette": "スレート × パール × ブルー",
            "colors": (("スレート", "#666970"), ("パール", "#E7E0D8"), ("ブルー", "#4269A8")),
            "color_style": "ニュートラル",
            "color_tip": "スレートとパールを軸に、スカーフのブルーを顔まわりに。",
            "hot_top": "ノースリーブトップス＋薄手シャツ",
            "mild_top": "バンドカラーシャツ",
            "cool_top": "ハイネックニット",
            "bottom": "ワイドデニム",
            "light_outer": "シャツブルゾン",
            "mid_outer": "オーバーサイズジャケット",
            "cold_outer": "ロングパファーコート",
            "shoes": "ボリュームスニーカー",
            "accessory": "トライアングルスカーフ",
        },
    ),
}

_COLOR_PRESETS = {
    "赤×ブルー": (
        (("コバルトブルー", "#315FAD"), ("アイボリー", "#F1EBDD"), ("チェリーレッド", "#B52D45")),
        "ブルーを主役に、赤を差し色として小物に一点投入。",
    ),
    "アースカラー": (
        (("オリーブ", "#78816A"), ("トープ", "#B9A899"), ("テラコッタ", "#B46A4E")),
        "オリーブとトープをベースに、テラコッタを小さく効かせて。",
    ),
    "ニュートラル": (
        (("パール", "#E7E0D8"), ("グレージュ", "#BBB4AE"), ("ワイン", "#713C56")),
        "パールとグレージュを重ね、ワイン色で秋冬らしい奥行きをプラス。",
    ),
}

_MONO_PALETTES = {
    "シティ・ユーティリティ": (
        (("スモークブラック", "#292A2F"), ("スチールグレー", "#777A80"), ("アイスシルバー", "#D8D9DC")),
        "黒を土台に、スチールグレーと冷たいシルバーで都会的に。",
    ),
    "ネオ・プレッピー": (
        (("インクブラック", "#202126"), ("パールグレー", "#C3C2C0"), ("チョークホワイト", "#F5F3EE")),
        "白を多めにして軽さを出し、黒い小物でプレッピーに引き締めて。",
    ),
    "スポーツ・ミックス": (
        (("ジェットブラック", "#17181B"), ("カーボングレー", "#696D74"), ("メタリックシルバー", "#C9CBD0")),
        "黒からシルバーへのコントラストで、スポーティな立体感を。",
    ),
    "リラックス・デニム": (
        (("チョークホワイト", "#F3F1EC"), ("ミストグレー", "#B7B9BC"), ("スレート", "#5B5F67")),
        "明るいグレーを中心にして、デニムのリラックス感をクリーンに。",
    ),
    "グレー・レザーMIX": (
        (("ピッチブラック", "#141519"), ("アッシュグレー", "#85858A"), ("ペールグレー", "#D4D3D1")),
        "黒いレザーとアッシュグレーの質感差で、単調さを回避。",
    ),
    "シアー・レイヤード": (
        (("パールホワイト", "#F1ECE5"), ("フォググレー", "#B5B4B3"), ("グラファイト", "#424349")),
        "明るいニュートラルを重ね、濃いグレーを小面積で効かせて。",
    ),
    "レトロ・プレッピー": (
        (("チョーク", "#F4F1EA"), ("ストーングレー", "#A9A7A3"), ("インク", "#27282D")),
        "白とストーングレーで柔らかく、インク色の靴で重心を作って。",
    ),
    "ワントーン・モード": (
        (("グラファイト", "#36373C"), ("ウォームグレー", "#A8A5A1"), ("ペールシルバー", "#D8D8D9")),
        "暖色寄りのグレーを挟み、同じ無彩色でも表情に変化を。",
    ),
    "アクティブ・シティ": (
        (("シルバーグレー", "#C7C9CD"), ("カーボン", "#393A3F"), ("ホワイト", "#FAF9F7")),
        "明るいグレーを主役に、黒のスポーツ小物でメリハリを。",
    ),
    "ダークロマンティック": (
        (("ソフトブラック", "#1B1A1F"), ("ダブグレー", "#77767C"), ("パール", "#E9E5DE")),
        "黒とダブグレーで深みを出し、パール色を顔まわりに。",
    ),
    "キャンパス・レトロ": (
        (("チョーク", "#F3F1EC"), ("ペブルグレー", "#AAA9A7"), ("インク", "#292A2F")),
        "チョークをベースに、インク色でプレッピーな輪郭を。",
    ),
    "テック・トレイル": (
        (("ストームグレー", "#777A80"), ("カーボン", "#35363B"), ("アイス", "#D9DADD")),
        "グレーの異なる明度を組み合わせ、テック素材の質感を見せて。",
    ),
    "スカーフ・クラシック": (
        (("パールグレー", "#D1CFCC"), ("グラファイト", "#414248"), ("チョーク", "#F5F2EC")),
        "明るいグレーとチョークを重ね、濃い色の小物で顔まわりを引き締めて。",
    ),
    "カラーブロック・プレッピー": (
        (("オフホワイト", "#F3EFE8"), ("クールグレー", "#A4A6AB"), ("ジェット", "#24252A")),
        "オフホワイトを主役にして、グレーと黒で軽やかなプレッピーに。",
    ),
    "グレー・テクスチャーミックス": (
        (("ライトグレージュ", "#D0CBC4"), ("スレート", "#676970"), ("ブラック", "#24252A")),
        "淡いグレージュとスレートの素材差で、ワントーンに奥行きを。",
    ),
    "スカーフ・シティ": (
        (("パール", "#E7E0D8"), ("ダブグレー", "#85868B"), ("ミッドナイト", "#303139")),
        "パールを顔まわりに置き、濃淡グレーを下半身にまとめて。",
    ),
}


def seasonal_trends(day: date) -> tuple[str, ...]:
    month = day.month
    if month in (3, 4, 5):
        season = "spring"
    elif month in (6, 7, 8):
        season = "summer"
    elif month in (9, 10, 11):
        season = "autumn"
    else:
        season = "winter"
    return _SEASONAL_TRENDS[season]


def _needs_precipitation_gear(weather: Weather) -> bool:
    precipitation_codes = {
        51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77,
        80, 81, 82, 85, 86, 95, 96, 99,
    }
    return weather.rain_probability >= 40 or weather.code in precipitation_codes


def _outerwear(weather: Weather, outfit: dict) -> str:
    if weather.high <= 12 or (weather.feels_like <= 8 and weather.high <= 20):
        layer = outfit["cold_outer"]
    elif weather.high <= 19 or (weather.feels_like <= 14 and weather.high <= 24):
        layer = outfit["mid_outer"]
    elif weather.low <= 19 or (weather.feels_like <= 20 and weather.high < 27):
        layer = outfit["light_outer"]
    else:
        layer = "アウターなし"

    if _needs_precipitation_gear(weather):
        if layer == "アウターなし":
            layer = "撥水ライトシェル"
        else:
            layer += "＋撥水レイヤー"
    elif weather.wind_speed >= 25:
        if layer == "アウターなし":
            layer = "軽量ウィンドシェル"
        else:
            layer += "（風を通しにくい素材がおすすめ）"
    return layer


def _top(weather: Weather, outfit: dict) -> str:
    if weather.high >= 27:
        top = outfit["hot_top"]
    elif weather.high >= 21:
        top = outfit["mild_top"]
    else:
        top = outfit["cool_top"]

    if weather.low <= 8 or weather.feels_like <= 12:
        top += "＋保温インナー"
    if weather.current_temperature >= 24 and weather.humidity >= 75:
        top += "（通気性を重視）"
    return top


def _reason(weather: Weather) -> str:
    details = [
        f"最高{weather.high:.0f}°C・最低{weather.low:.0f}°C"
        f"／現在の体感{weather.feels_like:.0f}°Cを考慮"
    ]
    if _needs_precipitation_gear(weather):
        details.append(f"降水確率{weather.rain_probability}%なので足元は雨対策")
    elif weather.wind_speed >= 25:
        details.append("風が強めなので軽い羽織りが便利")
    else:
        details.append("軽快に動けるバランス")
    if weather.current_temperature >= 24 and weather.humidity >= 75:
        details.append("湿度が高めなので通気性を重視")
    return " / ".join(details)


def recommend_outfits(
    weather: Weather,
    audience: str,
    day: date,
    count: int = 5,
    preferred_style: str = "おまかせ",
    preferred_palette: str = "おまかせ",
) -> list[Outfit]:
    if audience not in _WARDROBE:
        raise ValueError(f"対応していないスタイル区分です: {audience}")
    if count < 1 or count > 5:
        raise ValueError("おすすめ数は1〜5の範囲で指定してください。")
    available_palettes = {*_COLOR_PRESETS, "モノトーン"}
    if preferred_palette != "おまかせ" and preferred_palette not in available_palettes:
        raise ValueError(f"対応していないカラーコーデです: {preferred_palette}")

    active_trends = seasonal_trends(day)
    score_groups: dict[int, list[tuple[dict, str]]] = {}
    for item in _WARDROBE[audience]:
        matching_trends = [trend for trend in item["trends"] if trend in active_trends]
        score = int(bool(matching_trends))
        if preferred_style == item["style"]:
            score += 2
        trend = matching_trends[0] if matching_trends else item["trends"][0]
        score_groups.setdefault(score, []).append((item, trend))

    location_seed = int(
        sha256(f"{weather.city}|{audience}|{preferred_style}".encode()).hexdigest()[:8],
        16,
    )
    candidates = []
    for score in sorted(score_groups, reverse=True):
        group = score_groups[score]
        offset = (day.toordinal() + location_seed) % len(group)
        rotated_group = group[offset:] + group[:offset]
        candidates.extend((item, trend) for item, trend in rotated_group)

    results = []
    for item, trend in candidates[:count]:
        if preferred_palette == "おまかせ":
            colors = item["colors"]
            color_style = item["color_style"]
            color_tip = item["color_tip"]
        elif preferred_palette == "モノトーン":
            colors, color_tip = _MONO_PALETTES[item["title"]]
            color_style = preferred_palette
        else:
            colors, color_tip = _COLOR_PRESETS[preferred_palette]
            color_style = preferred_palette
        palette = " × ".join(name for name, _ in colors)

        accessory = item["accessory"]
        shoes = item["shoes"]
        if _needs_precipitation_gear(weather):
            shoes = "撥水仕様の" + shoes
            accessory += "＋折りたたみ傘"
        elif weather.wind_speed >= 25:
            accessory += "＋風よけ小物"

        results.append(
            Outfit(
                title=item["title"],
                style=item["style"],
                trend=trend,
                palette=palette,
                colors=colors,
                color_style=color_style,
                color_tip=color_tip,
                top=_top(weather, item),
                bottom=item["bottom"],
                outerwear=_outerwear(weather, item),
                shoes=shoes,
                accessory=accessory,
                reason=_reason(weather),
            )
        )
    return results
