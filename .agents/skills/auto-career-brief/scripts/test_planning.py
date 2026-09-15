import copy
import unittest
from test_collection import sample
from test_insight import analysis
import planning

def fixture():
    a=analysis()
    a['schema_version']=2
    a['analyses'][0]['planning']={
        'summary':'판매 변화를 비교해 상품 구성을 검토한다.',
        'comparison':[{'target':'기존 상품','known':'비교 설계','unknown':'실측 미확인'}],
        'hypothesis':{'text':'가설일 수 있다.','basis':'사실 1','verify':'대조군 비교','refute':'차이가 없는 경우'},
        'roles':{'product':'고객을 비교해 구성을 결정한다.','business':'이익을 비교해 지속 여부를 결정한다.'},
        'decisions':[{'kpi':'판매량','basis':'같은 기간','supports':'유지 검토','otherwise':'구성 조정'}]}
    return a

class PlanningTests(unittest.TestCase):
    def test_facts_and_input_preserved(self):
        c,a=sample(),fixture()
        before=copy.deepcopy((c,a))
        r=planning.combine(c,a)
        self.assertEqual((c,a),before)
        for k in ('summary','source','my_thought'):
            self.assertEqual(r['items'][0][k],c['items'][0][k])
        i=r['items'][0]['career_insight']
        self.assertIn('기획 가설',planning.analysis_body(i))
        self.assertIn('직접 작성',planning.exercise_body(i))

    def test_missing_comparison_or_refutation_rejected(self):
        for field in ('comparison','hypothesis','roles','decisions'):
            a=fixture()
            del a['analyses'][0]['planning'][field]
            with self.assertRaises(ValueError): planning.combine(sample(),a)
        a=fixture()
        a['analyses'][0]['planning']['hypothesis']['refute']=''
        with self.assertRaises(ValueError): planning.combine(sample(),a)

    def test_every_kpi_has_exactly_one_decision(self):
        for names in ([],['다른지표'],['판매량','판매량']):
            a=fixture();p=a['analyses'][0]['planning']
            d=p['decisions'][0]
            p['decisions']=[dict(d,kpi=n) for n in names]
            with self.assertRaises(ValueError): planning.combine(sample(),a)

    def test_long_or_multiline_summary_rejected(self):
        for summary in ('가'*91,'한줄\n두줄','첫줄<br>둘째줄'):
            a=fixture();a['analyses'][0]['planning']['summary']=summary
            with self.assertRaises(ValueError): planning.combine(sample(),a)

    def test_user_result_and_legacy_input_rejected(self):
        a=fixture();a['analyses'][0]['planning']['my_thought']='대신 작성'
        with self.assertRaises(ValueError): planning.combine(sample(),a)
        with self.assertRaises(ValueError): planning.combine(sample(),analysis())

if __name__=='__main__':
    unittest.main()
