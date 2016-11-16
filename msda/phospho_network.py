import pandas as pd
import networkx as nx
import requests
import numpy as np
import re
import subprocess
import mapping

file = ('/Users/kartik/Dropbox (HMS-LSP)/BrCaLines_profiling/'
        'RAWDATA/massspec/run2015/ReplicateA_pSTY_Summary_031315.xlsx')

df_ptm = pd.read_table('resources/Regulatory_sites_appended.tsv',
                       error_bad_lines=False)
df_kinase = pd.read_csv('resources/kinase_substrate_dataset.csv')
# df_networkin = pd.read_table('resources/networkin_human_predictions.tsv')
df_networkin = pd.read_csv('resources/networkin_human'
                           '_predictions_appended.csv')


def rename_columns(df):
    df = df.rename(columns={'Protein Id': 'Protein_ID',
                            'proteinID': 'Protein_ID',
                            'Site Position': 'Site_Position',
                            # 'siteIDstr': 'Site_Position',
                            'geneSymbol': 'Gene_Symbol',
                            'gene_symbol': 'Gene_Symbol',
                            'Gene Symbol': 'Gene_Symbol',
                            'motifPeptideStr': 'Motif',
                            'Localization score': 'Max Score'})
    return df


def split_sites(df, diff=None):
    # split
    df = rename_columns(df)
    uids, names, motifs, sites, mx, fc = [], [], [], [], [], []
    for index in range(len(df)):
        motif = df.Motif.iloc[index]
        motif_list = motif.split(';')
        site = str(df.Site_Position.iloc[index])
        site_list = site.split(';')
        uids += [df.Protein_ID.iloc[index]] * len(motif_list)
        names += [df.Gene_Symbol.iloc[index]] * len(motif_list)
        motifs += motif_list
        sites += site_list
        mx_score = str(df['Max Score'].iloc[index]).split(';')
        mx += mx_score
        if diff is not None:
            fc += [df[diff].iloc[index]] * len(motif_list)
    uids = [id.split('|')[1] for id in uids]
    sites = ['%s%s' % (m[6], s) for m, s in zip(motifs, sites)]
    if diff is None:
        df_clean = pd.DataFrame(zip(uids, names, motifs, sites, mx),
                                columns=('Protein_ID', 'Gene_Symbol',
                                         'Motif', 'Site', 'score'))
    else:
        df_clean = pd.DataFrame(zip(uids, names, motifs, sites, mx, fc),
                                columns=('Protein_ID', 'Gene_Symbol',
                                         'Motif', 'Site', 'score', 'fc'))

    return df_clean


def get_annotated_subset(df_input):
    df_input.Motif = [m[1:-1] for m in df_input.Motif.tolist()]
    psp_motifs = [m.upper()[2:-2] for m  #
                  in df_kinase['SITE_+/-7_AA'].tolist()]
    nkin_motifs = [m.upper() for m
                   in df_networkin.sequence.tolist()]
    all_motifs = list(set(psp_motifs+nkin_motifs))
    df_annotated = df_input[df_input.Motif.isin(all_motifs)]
    df_unannotated = df_input[~df_input.Motif.isin(all_motifs)]
    return df_annotated, df_unannotated


def generate_network(df_output):
    G = nx.MultiDiGraph()
    for index in range(len(df_output)):
        kinase = df_output.KINASE.iloc[index]
        kinase_id = df_output.KINASE_ID.iloc[index]
        substrate = df_output.Gene_Symbol.iloc[index]
        sub_id = df_output.Protein_ID.iloc[index]
        site = df_output.Site.iloc[index]
        G.add_node(substrate, UP=sub_id)
        G.add_node(kinase, UP=kinase_id)
        G.add_edge(kinase, substrate, site=site)
    return G


def generate_ksea_library(kin_sub_table, set_size=25):
    df = pd.read_csv(kin_sub_table)
    all_kinases = list(set(df.KINASE.tolist()))
    gene_sets = []

    for kinase in all_kinases:
        df1 = df[df.KINASE == kinase]
        subs = [str(g).upper() for g in df1.Gene_Symbol.tolist()]
        sites = df1.Site.tolist()
        sub_sites = list(set(['%s_%s' % (sub, site) for sub, site
                              in zip(subs, sites)]))
        if len(sub_sites) >= set_size:
            gene_set = [kinase, ' '] + sub_sites
            gene_sets.append('\t'.join(gene_set))
    return gene_sets


def generate_substrate_fasta(df):
    substrate_fasta = []
    ids, aa, pos = [], [], []
    for substrate in df.Protein_ID.tolist():
        r = requests.get('http://www.uniprot.org/uniprot/%s.fasta' %
                         substrate)
        # substrate_fasta.append(r.text)
        seq_lines = r.text.split('\n')
        sequence = ''.join(seq_lines[1:])
        id_line = seq_lines[0]
        try:
            # id = re.search('>(.*)HUMAN', id_line).group(1) + 'HUMAN'
            id = re.search('>(?:sp|tr)\|(.*)\|', id_line).group(1)
            ids.append(id)
            # seq_lines[0] = id
            substrate_fasta.append(">%s\n%s\n" % (id, sequence))
            site = df.Site[df.Protein_ID == substrate].values[0]
            aa.append(site[0])
            pos.append(site[1:])
        except AttributeError:
            print substrate
    df2 = pd.DataFrame(zip(ids, pos, aa))
    return substrate_fasta, df2


def create_rnk_file(df_input):
    fc = df_input.fc.tolist()
    gene = [g.upper() for g in df_input.Gene_Symbol.tolist()]
    site = df_input.Site.tolist()

    id = ["%s_%s" % (g, s) for g, s in zip(gene, site)]
    df_rnk = pd.DataFrame(zip(id, fc), columns=('ps_id', 'fc'))
    df_rnk = df_rnk.sort(['fc'], ascending=True)
    return df_rnk


def run_networkin(fasfile, psitefile, outfile):
    f = open(outfile, 'wb')
    subprocess.call(['resources/NetworKIN_release3.0/NetworKIN.py',
                     '-n', 'resources/NetPhorest/netphorest',
                     '-b', 'resources/blast-2.2.17/bin/blastall', '9606',
                     fasfile, psitefile], stdout=f)
    return


def get_networkin_kinases(motif, df_nt):
    motifp = motif[:5] + motif[5].lower() + motif[6:]

    precomputed_kinases = df_networkin[df_networkin.sequence == motifp][
        'string_identifier'].values.tolist()
    computed_kinases = df_nt[df_nt['Peptide sequence window'] == motifp][
        'Kinase/Phosphatase/Phospho-binding domain STRING ID'].values.tolist()

    kinase_enps = list(set(precomputed_kinases + computed_kinases))
    kinase_uids = [mapping.ensp2uid(id) for id in kinase_enps]
    return kinase_uids


def get_kinases(motif, organism=None):
    if organism:
        df_org = df_kinase[df_kinase.SUB_ORGANISM == organism]
    else:
        df_org = df_kinase
    df_org['MOTIF'] = [mtf[2:-2].upper()
                       for mtf in df_org['SITE_+/-7_AA'].tolist()]

    kinases = df_org.KINASE[df_org.MOTIF == motif].values.tolist()
    kinase_ids = df_org.KIN_ACC_ID[df_org.MOTIF == motif].values.tolist()
    kin_orgs = df_org.KIN_ORGANISM[df_org.MOTIF == motif].values.tolist()
    sub_orgs = df_org.SUB_ORGANISM[df_org.MOTIF == motif].values.tolist()

    return kinases, kinase_ids, kin_orgs, sub_orgs


def generate_kinase_table(df_input_kinase, df_nt):
    df_input_kinase = df_input_kinase.drop_duplicates()
    substrate, site, kinase_ids, source, motifs = [], [], [], [], []
    for ind, motif in enumerate(df_input_kinase.Motif.tolist()):
        out = get_kinases(motif)
        kinase_ids += out[1]
        source += ['PSP'] * len(out[1])
        nkins = get_networkin_kinases(motif, df_nt)
        kinase_ids += nkins
        source += ['Networkin'] * len(nkins)
        substrate += [df_input_kinase.Gene_Symbol.iloc[ind]] * (
            len(out[1]) + len(nkins))
        site += [df_input_kinase.Site.iloc[ind]] * (
            len(out[1]) + len(nkins))
        motifs += [motif] * (len(out[1]) + len(nkins))
        
    df_output = pd.DataFrame(zip(substrate, site, motifs,
                                 kinase_ids, source),
                             columns=['Gene_Symbol', 'Site', 'Motif',
                                      'KINASE_ID', 'source'])
    return df_output


def get_fc(df_input, samples, base_sample):
    df = df_input[samples].div(df_input[base_sample], axis=0)
    df = df.apply(np.log2)
    return df
