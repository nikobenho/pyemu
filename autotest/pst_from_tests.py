import os
import sys
import platform

# sys.path.append(os.path.join("..","pyemu"))
import pyemu
from pyemu import os_utils
from pyemu.prototypes.pst_from import PstFrom
import shutil

ext = ''
bin_path = os.path.join("..", "..", "bin")
if "linux" in platform.platform().lower():
    bin_path = os.path.join(bin_path, "linux")
elif "darwin" in platform.platform().lower():
    bin_path = os.path.join(bin_path, "mac")
else:
    bin_path = os.path.join(bin_path, "win")
    ext = '.exe'

mf_exe_name = os.path.join(bin_path, "mfnwt")
mt_exe_name = os.path.join(bin_path, "mt3dusgs")
mf6_exe_name = os.path.join(bin_path, "mf6")
pp_exe_name = os.path.join(bin_path, "pestpp")
ies_exe_name = os.path.join(bin_path, "pestpp-ies")
swp_exe_name = os.path.join(bin_path, "pestpp-swp")


def freyberg_test():
    import numpy as np
    import pandas as pd
    pd.set_option('display.max_rows', 500)
    pd.set_option('display.max_columns', 500)
    pd.set_option('display.width', 1000)
    try:
        import flopy
    except:
        return

    ext = ''
    bin_path = os.path.join("..", "..", "bin")
    if "linux" in platform.platform().lower():
        bin_path = os.path.join(bin_path, "linux")
    elif "darwin" in platform.platform().lower():
        bin_path = os.path.join(bin_path, "mac")
    else:
        bin_path = os.path.join(bin_path, "win")
        ext = '.exe'

    org_model_ws = os.path.join("..", "examples", "freyberg_sfr_update")
    nam_file = "freyberg.nam"
    m = flopy.modflow.Modflow.load(nam_file, model_ws=org_model_ws,
                                   check=False, forgive=False,
                                   exe_name=mf_exe_name)
    flopy.modflow.ModflowRiv(m, stress_period_data={
        0: [[0, 0, 0, m.dis.top.array[0, 0], 1.0, m.dis.botm.array[0, 0, 0]],
            [0, 0, 1, m.dis.top.array[0, 1], 1.0, m.dis.botm.array[0, 0, 1]],
            [0, 0, 1, m.dis.top.array[0, 1], 1.0, m.dis.botm.array[0, 0, 1]]]})

    org_model_ws = "temp_pst_from"
    if os.path.exists(org_model_ws):
        shutil.rmtree(org_model_ws)
    m.external_path = "."
    m.change_model_ws(org_model_ws)
    m.write_input()
    print("{0} {1}".format(mf_exe_name, m.name + ".nam"), org_model_ws)
    os_utils.run("{0} {1}".format(mf_exe_name, m.name + ".nam"),
                 cwd=org_model_ws)
    hds_kperk = []
    for k in range(m.nlay):
        for kper in range(m.nper):
            hds_kperk.append([kper, k])
    hds_runline, df = pyemu.gw_utils.setup_hds_obs(
        os.path.join(m.model_ws, f"{m.name}.hds"), kperk_pairs=None, skip=None,
        prefix="hds", include_path=False)

    sfo = flopy.utils.SfrFile(os.path.join(m.model_ws, 'freyberg.sfr.out'))
    sfodf = sfo.get_dataframe()
    sfodf[['kstp', 'kper']] = pd.DataFrame(sfodf.kstpkper.to_list(),
                                           index=sfodf.index)
    sfodf = sfodf.drop('kstpkper', axis=1)
    # just adding a bit of header in for test purposes
    sfo_pp_file = os.path.join(m.model_ws, 'freyberg.sfo.dat')
    with open(sfo_pp_file, 'w') as fp:
        fp.writelines(["This is a post processed sfr output file\n",
                      "Processed into tabular form using the lines:\n",
                      "sfo = flopy.utils.SfrFile('freyberg.sfr.out')\n",
                      "sfo.get_dataframe().to_csv('freyberg.sfo.dat')\n"])
        sfodf.to_csv(fp, sep=' ', index_label='idx')
    sfodf.to_csv(os.path.join(m.model_ws, 'freyberg.sfo.csv'),
                 index_label='idx')
    template_ws = "new_temp"
    # sr0 = m.sr
    sr = pyemu.helpers.SpatialReference.from_namfile(
        os.path.join(m.model_ws, m.namefile),
        delr=m.dis.delr, delc=m.dis.delc)
    # set up PstFrom object
    pf = PstFrom(original_d=org_model_ws, new_d=template_ws,
                 remove_existing=True,
                 longnames=True, spatial_reference=sr,
                 zero_based=False)
    # obs
    #   using tabular style model output
    #   (generated by pyemu.gw_utils.setup_hds_obs())
    pf.add_observations('freyberg.hds.dat', insfile='freyberg.hds.dat.ins2',
                        index_cols='obsnme', use_cols='obsval', prefix='hds')
    #   using the ins file generated by pyemu.gw_utils.setup_hds_obs()
    pf.add_observations_from_ins(ins_file='freyberg.hds.dat.ins')
    pf.post_py_cmds.append(hds_runline)
    pf.tmp_files.append(f"{m.name}.hds")
    # sfr outputs to obs
    pf.add_observations('freyberg.sfo.dat', insfile=None,
                        index_cols=['segment', 'reach', 'kstp', 'kper'],
                        use_cols=["Qaquifer", "Qout"], prefix='sfr',
                        ofile_skip=4, ofile_sep=' ')
    pf.tmp_files.append(f"{m.name}.sfr.out")
    pf.extra_py_imports.append('flopy')
    pf.post_py_cmds.extend(
        ["sfo_pp_file = 'freyberg.sfo.dat'",
         "sfo = flopy.utils.SfrFile('freyberg.sfr.out')",
         "sfodf = sfo.get_dataframe()",
         "sfodf[['kstp', 'kper']] = pd.DataFrame(sfodf.kstpkper.to_list(), index=sfodf.index)",
         "sfodf = sfodf.drop('kstpkper', axis=1)",
         "with open(sfo_pp_file, 'w') as fp:",
         "    fp.writelines(['This is a post processed sfr output file\\n', "
         "'Processed into tabular form using the lines:\\n', "
         "'sfo = flopy.utils.SfrFile(`freyberg.sfr.out`)\\n', "
         "'sfo.get_dataframe().to_csv(`freyberg.sfo.dat`)\\n'])",
         "    sfodf.to_csv(fp, sep=' ', index_label='idx')"])
    # csv version of sfr obs
    # sfr outputs to obs
    pf.add_observations('freyberg.sfo.csv', insfile=None,
                        index_cols=['segment', 'reach', 'kstp', 'kper'],
                        use_cols=["Qaquifer", "Qout"], prefix='sfr2',
                        ofile_sep=',')
    pf.post_py_cmds.append(
        "sfodf.to_csv('freyberg.sfo.csv', sep=',', index_label='idx')")

    # pars
    pf.add_parameters(filenames="RIV_0000.dat", par_type="grid",
                      index_cols=[0, 1, 2], use_cols=[3, 5],
                      par_name_base=["rivstage_grid", "rivbot_grid"],
                      mfile_fmt='%10d%10d%10d %15.8F %15.8F %15.8F',
                      pargp='rivbot')
    pf.add_parameters(filenames="RIV_0000.dat", par_type="grid",
                      index_cols=[0, 1, 2], use_cols=4)
    pf.add_parameters(filenames=["WEL_0000.dat", "WEL_0001.dat"],
                      par_type="grid", index_cols=[0, 1, 2], use_cols=3,
                      par_name_base="welflux_grid",
                      zone_array=m.bas6.ibound.array)
    pf.add_parameters(filenames=["WEL_0000.dat"], par_type="constant",
                      index_cols=[0, 1, 2], use_cols=3,
                      par_name_base=["flux_const"])
    pf.add_parameters(filenames="rech_1.ref", par_type="grid",
                      zone_array=m.bas6.ibound[0].array,
                      par_name_base="rch_datetime:1-1-1970")
    pf.add_parameters(filenames=["rech_1.ref", "rech_2.ref"],
                      par_type="zone", zone_array=m.bas6.ibound[0].array)
    pf.add_parameters(filenames="rech_1.ref", par_type="pilot_point",
                      zone_array=m.bas6.ibound[0].array,
                      par_name_base="rch_datetime:1-1-1970", pp_space=4)
    pf.add_parameters(filenames="rech_1.ref", par_type="pilot_point",
                      zone_array=m.bas6.ibound[0].array,
                      par_name_base="rch_datetime:1-1-1970", pp_space=1,
                      ult_ubound=100, ult_lbound=0.0)

    # add model run command
    pf.mod_sys_cmds.append("{0} {1}".format(mf_exe_name, m.name + ".nam"))
    print(pf.mult_files)
    print(pf.org_files)


    # build pest
    pst = pf.build_pst('freyberg.pst')

    # check mult files are in pst input files
    csv = os.path.join(template_ws, "mult2model_info.csv")
    df = pd.read_csv(csv, index_col=0)
    mults_not_linked_to_pst = ((set(df.mlt_file.unique()) -
                                set(pst.input_files)) -
                               set(df.loc[df.pp_file.notna()].mlt_file))
    assert len(mults_not_linked_to_pst) == 0, print(mults_not_linked_to_pst)

    pst.write_input_files(pst_path=pf.new_d)
    # test par mults are working
    b_d = os.getcwd()
    os.chdir(pf.new_d)
    try:
        pyemu.helpers.apply_list_and_array_pars(
            arr_par_file="mult2model_info.csv")
    except Exception as e:
        os.chdir(b_d)
        raise Exception(str(e))
    os.chdir(b_d)

    pst.control_data.noptmax = 0
    pst.write(os.path.join(pf.new_d, "freyberg.pst"))
    pyemu.os_utils.run("{0} freyberg.pst".format(
        os.path.join(bin_path, "pestpp-ies")), cwd=pf.new_d)

    res_file = os.path.join(pf.new_d, "freyberg.base.rei")
    assert os.path.exists(res_file), res_file
    pst.set_res(res_file)
    print(pst.phi)
    assert pst.phi < 1.0e-5, pst.phi


def freyberg_prior_build_test():
    import numpy as np
    import pandas as pd
    pd.set_option('display.max_rows', 500)
    pd.set_option('display.max_columns', 500)
    pd.set_option('display.width', 1000)
    try:
        import flopy
    except:
        return

    ext = ''
    bin_path = os.path.join("..", "..", "bin")
    if "linux" in platform.platform().lower():
        bin_path = os.path.join(bin_path, "linux")
    elif "darwin" in platform.platform().lower():
        bin_path = os.path.join(bin_path, "mac")
    else:
        bin_path = os.path.join(bin_path, "win")
        ext = '.exe'

    org_model_ws = os.path.join("..", "examples", "freyberg_sfr_update")
    nam_file = "freyberg.nam"
    m = flopy.modflow.Modflow.load(nam_file, model_ws=org_model_ws,
                                   check=False, forgive=False,
                                   exe_name=mf_exe_name)
    flopy.modflow.ModflowRiv(m, stress_period_data={
        0: [[0, 0, 0, m.dis.top.array[0, 0], 1.0, m.dis.botm.array[0, 0, 0]],
            [0, 0, 1, m.dis.top.array[0, 1], 1.0, m.dis.botm.array[0, 0, 1]],
            [0, 0, 1, m.dis.top.array[0, 1], 1.0, m.dis.botm.array[0, 0, 1]]]})

    org_model_ws = "temp_pst_from"
    if os.path.exists(org_model_ws):
        shutil.rmtree(org_model_ws)
    m.external_path = "."
    m.change_model_ws(org_model_ws)
    m.write_input()
    print("{0} {1}".format(mf_exe_name, m.name + ".nam"), org_model_ws)
    os_utils.run("{0} {1}".format(mf_exe_name, m.name + ".nam"),
                 cwd=org_model_ws)
    hds_kperk = []
    for k in range(m.nlay):
        for kper in range(m.nper):
            hds_kperk.append([kper, k])
    hds_runline, df = pyemu.gw_utils.setup_hds_obs(
        os.path.join(m.model_ws, f"{m.name}.hds"), kperk_pairs=None, skip=None,
        prefix="hds", include_path=False)

    template_ws = "new_temp"
    # sr0 = m.sr
    sr = pyemu.helpers.SpatialReference.from_namfile(
        os.path.join(m.model_ws, m.namefile),
        delr=m.dis.delr, delc=m.dis.delc)
    # set up PstFrom object
    pf = PstFrom(original_d=org_model_ws, new_d=template_ws,
                 remove_existing=True,
                 longnames=True, spatial_reference=sr,
                 zero_based=False)
    # obs
    #   using tabular style model output
    #   (generated by pyemu.gw_utils.setup_hds_obs())
    pf.add_observations('freyberg.hds.dat', insfile='freyberg.hds.dat.ins2',
                        index_cols='obsnme', use_cols='obsval', prefix='hds')
    pf.post_py_cmds.append(hds_runline)
    pf.tmp_files.append(f"{m.name}.hds")

    # pars
    v = pyemu.geostats.ExpVario(contribution=1.0, a=2500)
    geostruct = pyemu.geostats.GeoStruct(
        variograms=v, transform='log')
    # Pars for river list style model file, every entry in columns 3 and 4
    # specifying formatted model file and passing a geostruct
    pf.add_parameters(filenames="RIV_0000.dat", par_type="grid",
                      index_cols=[0, 1, 2], use_cols=[3, 4],
                      par_name_base=["rivstage_grid", "rivcond_grid"],
                      mfile_fmt='%10d%10d%10d %15.8F %15.8F %15.8F',
                      geostruct=geostruct, lower_bound=[0.9, 0.01],
                      upper_bound=[1.1, 100.], ult_lbound=[0.3, None])
    # 2 constant pars applied to columns 3 and 4
    # this time specifying free formatted model file
    pf.add_parameters(filenames="RIV_0000.dat", par_type="constant",
                      index_cols=[0, 1, 2], use_cols=[3, 4],
                      par_name_base=["rivstage", "rivcond"],
                      mfile_fmt='free', lower_bound=[0.9, 0.01],
                      upper_bound=[1.1, 100.], ult_lbound=[None, 0.01])
    # pf.add_parameters(filenames="RIV_0000.dat", par_type="constant",
    #                   index_cols=[0, 1, 2], use_cols=5,
    #                   par_name_base="rivbot",
    #                   mfile_fmt='free', lower_bound=0.9,
    #                   upper_bound=1.1, ult_ubound=100.,
    #                   ult_lbound=0.001)
    # setting up temporal variogram for correlating temporal pars
    date = m.dis.start_datetime
    v = pyemu.geostats.ExpVario(contribution=1.0, a=180.0)  # 180 correlation length
    t_geostruct = pyemu.geostats.GeoStruct(variograms=v)
    # looping over temporal list style input files
    # setting up constant parameters for col 3 for each temporal file
    # making sure all are set up with same pargp and geostruct (to ensure correlation)
    # Parameters for wel list style
    well_mfiles = ["WEL_0000.dat", "WEL_0001.dat", "WEL_0002.dat"]
    for t, well_file in enumerate(well_mfiles):
        # passing same temporal geostruct and pargp,
        # date is incremented and will be used for correlation with
        pf.add_parameters(filenames=well_file, par_type="constant",
                          index_cols=[0, 1, 2], use_cols=3,
                          par_name_base="flux", alt_inst_str='kper',
                          datetime=date, geostruct=t_geostruct,
                          pargp='wellflux_t', lower_bound=0.25,
                          upper_bound=1.75)
        date = (pd.to_datetime(date) +
                pd.DateOffset(m.dis.perlen.array[t], 'day'))
    # par for each well (same par through time)
    pf.add_parameters(filenames=well_mfiles,
                      par_type="grid", index_cols=[0, 1, 2], use_cols=3,
                      par_name_base="welflux_grid",
                      zone_array=m.bas6.ibound.array,
                      geostruct=geostruct, lower_bound=0.25, upper_bound=1.75)
    # global constant across all files
    pf.add_parameters(filenames=well_mfiles,
                      par_type="constant",
                      index_cols=[0, 1, 2], use_cols=3,
                      par_name_base=["flux_global"],
                      lower_bound=0.25, upper_bound=1.75)

    # Spatial array style pars - cell-by-cell
    hk_files = ["hk_Layer_{0:d}.ref".format(i) for i in range(1, 4)]
    for hk in hk_files:
        pf.add_parameters(filenames=hk, par_type="grid",
                          zone_array=m.bas6.ibound[0].array,
                          par_name_base="hk", alt_inst_str='lay',
                          geostruct=geostruct,
                          lower_bound=0.01, upper_bound=100.)

    # Pars for temporal array style model files
    date = m.dis.start_datetime  # reset date
    rch_mfiles = ["rech_0.ref", "rech_1.ref", "rech_2.ref"]
    for t, rch_file in enumerate(rch_mfiles):
        # constant par for each file but linked by geostruct and pargp
        pf.add_parameters(filenames=rch_file, par_type="constant",
                          zone_array=m.bas6.ibound[0].array,
                          par_name_base="rch", alt_inst_str='kper',
                          datetime=date, geostruct=t_geostruct,
                          pargp='rch_t', lower_bound=0.9, upper_bound=1.1)
        date = (pd.to_datetime(date) +
                pd.DateOffset(m.dis.perlen.array[t], 'day'))
    # spatially distributed array style pars - cell-by-cell
    # pf.add_parameters(filenames=rch_mfiles, par_type="grid",
    #                   zone_array=m.bas6.ibound[0].array,
    #                   par_name_base="rch",
    #                   geostruct=geostruct)
    pf.add_parameters(filenames=rch_mfiles, par_type="pilot_point",
                      zone_array=m.bas6.ibound[0].array,
                      par_name_base="rch", pp_space=1,
                      ult_ubound=None, ult_lbound=None,
                      geostruct=geostruct, lower_bound=0.9, upper_bound=1.1)
    # global constant recharge par
    pf.add_parameters(filenames=rch_mfiles, par_type="constant",
                      zone_array=m.bas6.ibound[0].array,
                      par_name_base="rch_global", lower_bound=0.9,
                      upper_bound=1.1)
    # zonal recharge pars
    pf.add_parameters(filenames=rch_mfiles,
                      par_type="zone", par_name_base='rch_zone',
                      lower_bound=0.9, upper_bound=1.1, ult_lbound=1.e-6,
                      ult_ubound=100.)


    # add model run command
    pf.mod_sys_cmds.append("{0} {1}".format(mf_exe_name, m.name + ".nam"))
    print(pf.mult_files)
    print(pf.org_files)


    # build pest
    pst = pf.build_pst('freyberg.pst')
    cov = pf.build_prior(fmt="ascii")
    pe = pf.draw(10, use_specsim=True)
    # check mult files are in pst input files
    csv = os.path.join(template_ws, "mult2model_info.csv")
    df = pd.read_csv(csv, index_col=0)
    mults_not_linked_to_pst = ((set(df.mlt_file.unique()) -
                                set(pst.input_files)) -
                               set(df.loc[df.pp_file.notna()].mlt_file))
    assert len(mults_not_linked_to_pst) == 0, print(mults_not_linked_to_pst)

    pst.write_input_files(pst_path=pf.new_d)
    # test par mults are working
    b_d = os.getcwd()
    os.chdir(pf.new_d)
    try:
        pyemu.helpers.apply_list_and_array_pars(
            arr_par_file="mult2model_info.csv")
    except Exception as e:
        os.chdir(b_d)
        raise Exception(str(e))
    os.chdir(b_d)

    pst.control_data.noptmax = 0
    pst.write(os.path.join(pf.new_d, "freyberg.pst"))
    pyemu.os_utils.run("{0} freyberg.pst".format(
        os.path.join(bin_path, "pestpp-ies")), cwd=pf.new_d)

    res_file = os.path.join(pf.new_d, "freyberg.base.rei")
    assert os.path.exists(res_file), res_file
    pst.set_res(res_file)
    print(pst.phi)
    assert pst.phi < 1.0e-5, pst.phi


def mf6_freyberg_test():
    import numpy as np
    import pandas as pd
    pd.set_option('display.max_rows', 500)
    pd.set_option('display.max_columns', 500)
    pd.set_option('display.width', 1000)
    try:
        import flopy
    except:
        return

    org_model_ws = os.path.join('..', 'examples', 'freyberg_mf6')
    tmp_model_ws = "temp_pst_from"
    if os.path.exists(tmp_model_ws):
        shutil.rmtree(tmp_model_ws)
    # os.mkdir(tmp_model_ws)
    # sim = flopy.mf6.MFSimulation.load(sim_ws=org_model_ws)
    # # sim.set_all_data_external()
    # sim.simulation_data.mfpath.set_sim_path(tmp_model_ws)
    # # sim.set_all_data_external()
    # m = sim.get_model("freyberg6")
    # sim.set_all_data_external()
    # sim.write_simulation()

    # to by pass the issues with flopy
    shutil.copytree(org_model_ws,tmp_model_ws)
    sim = flopy.mf6.MFSimulation.load(sim_ws=org_model_ws)
    m = sim.get_model("freyberg6")

    # SETUP pest stuff...
    os_utils.run("{0} ".format("mf6"),
                 cwd=tmp_model_ws)


    template_ws = "new_temp"
    # sr0 = m.sr
    sr = pyemu.helpers.SpatialReference.from_namfile(
        os.path.join(tmp_model_ws, "freyberg6.nam"),
        delr=m.dis.delr.array, delc=m.dis.delc.array)
    # set up PstFrom object
    pf = PstFrom(original_d=tmp_model_ws, new_d=template_ws,
                 remove_existing=True,
                 longnames=True, spatial_reference=sr,
                 zero_based=False,start_datetime="1-1-2018")
    # obs
    #   using tabular style model output
    #   (generated by pyemu.gw_utils.setup_hds_obs())
    # pf.add_observations('freyberg.hds.dat', insfile='freyberg.hds.dat.ins2',
    #                     index_cols='obsnme', use_cols='obsval', prefix='hds')

    df = pd.read_csv(os.path.join(tmp_model_ws,"heads.csv"),index_col=0)
    pf.add_observations("heads.csv",insfile="heads.csv.ins",index_cols="time",use_cols=list(df.columns.values),prefix="hds")
    df = pd.read_csv(os.path.join(tmp_model_ws, "sfr.csv"), index_col=0)
    pf.add_observations("sfr.csv", insfile="sfr.csv.ins", index_cols="time", use_cols=list(df.columns.values))
    v = pyemu.geostats.ExpVario(contribution=1.0,a=1000)
    gr_gs = pyemu.geostats.GeoStruct(variograms=v)
    wel_gs = pyemu.geostats.GeoStruct(variograms=v,name="wel")
    rch_temporal_gs = pyemu.geostats.GeoStruct(variograms=pyemu.geostats.ExpVario(contribution=1.0,a=60))
    pf.extra_py_imports.append('flopy')
    ib = m.dis.idomain[0].array
    tags = {"npf_k_":[0.1,10.],"npf_k33_":[.1,10],"sto_ss":[.1,10],"sto_sy":[.9,1.1],"rch_recharge":[.5,1.5]}
    dts = pd.to_datetime("1-1-2018") + pd.to_timedelta(np.cumsum(sim.tdis.perioddata.array["perlen"]),unit="d")
    print(dts)
    for tag,bnd in tags.items():
        lb,ub = bnd[0],bnd[1]
        arr_files = [f for f in os.listdir(tmp_model_ws) if tag in f and f.endswith(".txt")]
        if "rch" in tag:
            pf.add_parameters(filenames=arr_files, par_type="grid", par_name_base="rch_gr",
                              pargp="rch_gr", zone_array=ib, upper_bound=ub, lower_bound=lb,
                              geostruct=gr_gs)
            for arr_file in arr_files:
                kper = int(arr_file.split('.')[1].split('_')[-1]) - 1
                pf.add_parameters(filenames=arr_file,par_type="constant",par_name_base=arr_file.split('.')[1]+"_cn",
                                  pargp="rch_const",zone_array=ib,upper_bound=ub,lower_bound=lb,geostruct=rch_temporal_gs,
                                  datetime=dts[kper])
        else:
            for arr_file in arr_files:
                pf.add_parameters(filenames=arr_file,par_type="grid",par_name_base=arr_file.split('.')[1]+"_gr",
                                  pargp=arr_file.split('.')[1]+"_gr",zone_array=ib,upper_bound=ub,lower_bound=lb,
                                  geostruct=gr_gs)
                pf.add_parameters(filenames=arr_file, par_type="pilotpoints", par_name_base=arr_file.split('.')[1]+"_pp",
                                  pargp=arr_file.split('.')[1]+"_pp", zone_array=ib,upper_bound=ub,lower_bound=lb,)


    list_files = [f for f in os.listdir(tmp_model_ws) if "wel_stress_period_data" in f]
    for list_file in list_files:
        kper = list_file.split(".")[1].split('_')[-1]
        pf.add_parameters(filenames=list_file,par_type="grid",par_name_base="wel_{0}".format(kper),
                          pargp="wel_{0}".format(kper),index_cols=[0,1,2],use_cols=[3],
                          upper_bound=1.5,lower_bound=0.5, geostruct=gr_gs)

    # add model run command
    pf.mod_sys_cmds.append("mf6")
    print(pf.mult_files)
    print(pf.org_files)

    # build pest
    pst = pf.build_pst('freyberg.pst')

    num_reals = 100
    pe = pf.draw(num_reals, use_specsim=True)
    pe.to_binary(os.path.join(template_ws, "prior.jcb"))
    assert pe.shape[1] == pst.npar_adj, "{0} vs {1}".format(pe.shape[0], pst.npar_adj)
    assert pe.shape[0] == num_reals

    # test par mults are working
    b_d = os.getcwd()
    os.chdir(pf.new_d)
    try:
        pyemu.helpers.apply_list_and_array_pars(
            arr_par_file="mult2model_info.csv")
    except Exception as e:
        os.chdir(b_d)
        raise Exception(str(e))
    os.chdir(b_d)

    pst.control_data.noptmax = 0
    pst.pestpp_options["additional_ins_delimiters"] = ","

    pst.write(os.path.join(pf.new_d, "freyberg.pst"))
    pyemu.os_utils.run("{0} freyberg.pst".format(
        os.path.join("pestpp-ies")), cwd=pf.new_d)

    res_file = os.path.join(pf.new_d, "freyberg.base.rei")
    assert os.path.exists(res_file), res_file
    pst.set_res(res_file)
    print(pst.phi)
    #assert pst.phi < 1.0e-5, pst.phi



    # check mult files are in pst input files
    csv = os.path.join(template_ws, "mult2model_info.csv")
    df = pd.read_csv(csv, index_col=0)
    mults_not_linked_to_pst = ((set(df.mlt_file.unique()) -
                                set(pst.input_files)) -
                               set(df.loc[df.pp_file.notna()].mlt_file))
    assert len(mults_not_linked_to_pst) == 0, print(mults_not_linked_to_pst)


if __name__ == "__main__":
    # freyberg_test()
    # freyberg_prior_build_test()
    mf6_freyberg_test()
